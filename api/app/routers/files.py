from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
import uuid
import structlog
from pathlib import Path

from app.database.connection import get_db
from app.database.models import Dataset, DatasetVersion, DatasetFile, User
from app.schemas.datasets import DatasetFileResponse
from app.core.security import get_current_user
from app.services.file_manager import FileManagementService
from app.services.datalad_service import DataLadService
from app.main import get_file_manager, get_datalad_service
from app.config import settings

logger = structlog.get_logger()
router = APIRouter(prefix="/datasets/{dataset_id}/files")


@router.post("", response_model=List[DatasetFileResponse])
async def upload_files(
    dataset_id: str,
    files: List[UploadFile] = File(...),
    version_id: Optional[str] = Form(None),
    current_user: User = Depends(get_current_user),
    file_manager: FileManagementService = Depends(get_file_manager),
    datalad_service: DataLadService = Depends(get_datalad_service),
    db: AsyncSession = Depends(get_db)
):
    """Upload files to dataset"""
    
    try:
        from sqlalchemy import select
        import asyncio
        import tempfile
        import aiofiles
        
        # Verify dataset exists and user has access
        dataset_query = select(Dataset).where(
            Dataset.id == uuid.UUID(dataset_id),
            Dataset.deleted_at.is_(None)
        )
        
        result = await db.execute(dataset_query)
        dataset = result.scalar_one_or_none()
        
        if not dataset:
            raise HTTPException(status_code=404, detail="Dataset not found")
        
        # Check permissions
        if dataset.owner_id != current_user.id and not current_user.is_superuser:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        
        # Get or create version
        if version_id:
            version_query = select(DatasetVersion).where(
                DatasetVersion.id == uuid.UUID(version_id),
                DatasetVersion.dataset_id == uuid.UUID(dataset_id)
            )
            version_result = await db.execute(version_query)
            version = version_result.scalar_one_or_none()
            
            if not version:
                raise HTTPException(status_code=404, detail="Version not found")
        else:
            # Create new version for this upload
            version = DatasetVersion(
                dataset_id=uuid.UUID(dataset_id),
                version_name=f"upload-{uuid.uuid4().hex[:8]}",
                commit_hash="pending",
                created_by=current_user.id,
                message="File upload"
            )
            db.add(version)
            await db.commit()
            await db.refresh(version)
        
        # Process file uploads
        uploaded_files = []
        temp_files = []
        
        try:
            for file in files:
                # Validate file size
                if file.size and file.size > settings.max_file_size:
                    raise HTTPException(
                        status_code=413,
                        detail=f"File {file.filename} exceeds maximum size"
                    )
                
                # Create temporary file
                temp_file = Path(tempfile.mktemp(suffix=f"_{file.filename}"))
                temp_files.append(temp_file)
                
                # Save uploaded file
                async with aiofiles.open(temp_file, 'wb') as f:
                    content = await file.read()
                    await f.write(content)
                
                # Upload to S3
                s3_key = f"{dataset.s3_prefix}files/{version.id}/{file.filename}"
                upload_result = await file_manager.upload_file(
                    file_path=temp_file,
                    s3_key=s3_key,
                    metadata={
                        "dataset_id": dataset_id,
                        "version_id": str(version.id),
                        "uploaded_by": str(current_user.id),
                        "original_name": file.filename
                    }
                )
                
                # Create database record
                db_file = DatasetFile(
                    dataset_id=uuid.UUID(dataset_id),
                    version_id=version.id,
                    file_path=f"files/{file.filename}",
                    s3_key=s3_key,
                    file_size=upload_result["size"],
                    checksum=upload_result["sha256_checksum"],
                    mime_type=upload_result["content_type"]
                )
                
                db.add(db_file)
                uploaded_files.append(db_file)
            
            # Update version commit hash after DataLad processing
            # Add files to DataLad
            if uploaded_files:
                await datalad_service.add_files(
                    dataset_id=dataset.datalad_id,
                    file_paths=temp_files,
                    commit_message=f"Add {len(uploaded_files)} files"
                )
                
                # Get updated commit hash
                dataset_info = await datalad_service.get_dataset_info(dataset.datalad_id)
                version.commit_hash = dataset_info.get("commit_hash", "unknown")
            
            await db.commit()
            
            # Update dataset file count
            dataset.file_count += len(uploaded_files)
            dataset.total_size_bytes += sum(f.file_size or 0 for f in uploaded_files)
            await db.commit()
            
            logger.info("Files uploaded successfully", 
                       dataset_id=dataset_id, count=len(uploaded_files))
            
            return [DatasetFileResponse.from_orm(f) for f in uploaded_files]
            
        finally:
            # Cleanup temporary files
            for temp_file in temp_files:
                try:
                    if temp_file.exists():
                        temp_file.unlink()
                except Exception:
                    pass
            
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error("File upload failed", dataset_id=dataset_id, error=str(e))
        raise HTTPException(status_code=500, detail="File upload failed")


@router.get("", response_model=List[DatasetFileResponse])
async def list_files(
    dataset_id: str,
    version_id: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """List files in dataset"""
    
    try:
        from sqlalchemy import select
        
        # Verify dataset access
        dataset_query = select(Dataset).where(
            Dataset.id == uuid.UUID(dataset_id),
            Dataset.deleted_at.is_(None)
        )
        
        result = await db.execute(dataset_query)
        dataset = result.scalar_one_or_none()
        
        if not dataset:
            raise HTTPException(status_code=404, detail="Dataset not found")
        
        # Check access permissions
        if (dataset.visibility == "private" and 
            dataset.owner_id != current_user.id and
            not current_user.is_superuser):
            raise HTTPException(status_code=404, detail="Dataset not found")
        
        # Build query
        files_query = select(DatasetFile).where(
            DatasetFile.dataset_id == uuid.UUID(dataset_id)
        )
        
        if version_id:
            files_query = files_query.where(
                DatasetFile.version_id == uuid.UUID(version_id)
            )
        
        files_query = files_query.order_by(DatasetFile.created_at.desc())
        
        result = await db.execute(files_query)
        files = result.scalars().all()
        
        return [DatasetFileResponse.from_orm(f) for f in files]
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to list files", dataset_id=dataset_id, error=str(e))
        raise HTTPException(status_code=500, detail="Failed to list files")


@router.get("/{file_id}/download")
async def download_file(
    dataset_id: str,
    file_id: str,
    current_user: User = Depends(get_current_user),
    file_manager: FileManagementService = Depends(get_file_manager),
    db: AsyncSession = Depends(get_db)
):
    """Get presigned download URL for file"""
    
    try:
        from sqlalchemy import select
        
        # Verify file exists and user has access
        file_query = select(DatasetFile).join(Dataset).where(
            DatasetFile.id == uuid.UUID(file_id),
            DatasetFile.dataset_id == uuid.UUID(dataset_id),
            Dataset.deleted_at.is_(None)
        )
        
        result = await db.execute(file_query)
        file_record = result.scalar_one_or_none()
        
        if not file_record:
            raise HTTPException(status_code=404, detail="File not found")
        
        # Check dataset access
        dataset_query = select(Dataset).where(Dataset.id == uuid.UUID(dataset_id))
        result = await db.execute(dataset_query)
        dataset = result.scalar_one_or_none()
        
        if (dataset and dataset.visibility == "private" and 
            dataset.owner_id != current_user.id and
            not current_user.is_superuser):
            raise HTTPException(status_code=403, detail="Access denied")
        
        # Generate presigned URL
        if file_record.s3_key:
            download_url = await file_manager.generate_presigned_url(
                s3_key=file_record.s3_key,
                expiration=3600,  # 1 hour
                method="GET"
            )
            
            return {"download_url": download_url}
        else:
            raise HTTPException(status_code=404, detail="File not available for download")
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Download URL generation failed", 
                    dataset_id=dataset_id, file_id=file_id, error=str(e))
        raise HTTPException(status_code=500, detail="Failed to generate download URL")