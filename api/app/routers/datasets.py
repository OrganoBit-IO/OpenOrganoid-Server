from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional, Dict, Any
import uuid
import structlog

from app.database.connection import get_db
from app.database.models import Dataset, DatasetVersion, User
from app.schemas.datasets import (
    DatasetCreate, DatasetResponse, DatasetUpdate, DatasetListResponse,
    DatasetVersionCreate, DatasetVersionResponse
)
from app.core.security import get_current_user
from app.services.datalad_service import DataLadService
from app.services.cache_manager import CacheManager
from app.main import get_datalad_service, get_cache_manager

logger = structlog.get_logger()
router = APIRouter(prefix="/datasets")


@router.post("", response_model=DatasetResponse)
async def create_dataset(
    dataset_data: DatasetCreate,
    current_user: User = Depends(get_current_user),
    datalad_service: DataLadService = Depends(get_datalad_service),
    cache_manager: CacheManager = Depends(get_cache_manager),
    db: AsyncSession = Depends(get_db)
):
    """Create new dataset with DataLad initialization"""
    
    # Validate user permissions
    if not current_user.is_active:
        raise HTTPException(status_code=403, detail="User account is inactive")
    
    try:
        # Generate unique dataset ID
        dataset_id = str(uuid.uuid4())
        datalad_id = f"dataset-{dataset_id}"
        
        # Create DataLad dataset
        dataset_config = {
            "name": dataset_data.name,
            "description": dataset_data.description,
            "owner_id": str(current_user.id),
        }
        
        # Initialize DataLad dataset
        datalad_result = await datalad_service.create_dataset(
            dataset_id=datalad_id,
            metadata=dataset_config,
            s3_config=None  # Will be configured later with S3 settings
        )
        
        # Create database record
        db_dataset = Dataset(
            id=uuid.UUID(dataset_id),
            name=dataset_data.name,
            description=dataset_data.description,
            owner_id=current_user.id,
            organization_id=dataset_data.organization_id,
            visibility=dataset_data.visibility,
            datalad_id=datalad_id,
            s3_prefix=f"datasets/{dataset_id}/",
            metadata=dataset_data.metadata or {}
        )
        
        db.add(db_dataset)
        await db.commit()
        await db.refresh(db_dataset)
        
        # Cache dataset metadata
        await cache_manager.cache_dataset_metadata(
            dataset_id,
            {
                "id": str(db_dataset.id),
                "name": db_dataset.name,
                "description": db_dataset.description,
                "owner_id": str(db_dataset.owner_id),
                "visibility": db_dataset.visibility,
                "status": db_dataset.status,
                "created_at": db_dataset.created_at.isoformat(),
                "datalad_id": db_dataset.datalad_id
            }
        )
        
        logger.info("Dataset created successfully", 
                   dataset_id=dataset_id, name=dataset_data.name)
        
        return DatasetResponse.from_orm(db_dataset)
        
    except Exception as e:
        await db.rollback()
        logger.error("Dataset creation failed", error=str(e))
        raise HTTPException(status_code=500, detail="Dataset creation failed")


@router.get("", response_model=DatasetListResponse)
async def list_datasets(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    visibility: Optional[str] = Query(None),
    owner_id: Optional[str] = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """List datasets with filtering and pagination"""
    
    from sqlalchemy import select, and_, or_
    
    try:
        # Build query with access control
        query = select(Dataset).where(Dataset.deleted_at.is_(None))
        
        # Apply visibility filters based on user permissions
        if not current_user.is_superuser:
            access_conditions = [
                Dataset.owner_id == current_user.id,  # User owns the dataset
                and_(
                    Dataset.visibility == "public"  # Public datasets
                ),
                # TODO: Add organization membership check
            ]
            query = query.where(or_(*access_conditions))
        
        # Apply additional filters
        if visibility:
            query = query.where(Dataset.visibility == visibility)
        if owner_id:
            query = query.where(Dataset.owner_id == uuid.UUID(owner_id))
        
        # Apply pagination
        query = query.offset(skip).limit(limit)
        
        result = await db.execute(query)
        datasets = result.scalars().all()
        
        # Get total count for pagination
        count_query = select(Dataset).where(Dataset.deleted_at.is_(None))
        if not current_user.is_superuser:
            count_query = count_query.where(or_(*access_conditions))
        
        count_result = await db.execute(count_query)
        total_count = len(count_result.scalars().all())
        
        return DatasetListResponse(
            datasets=[DatasetResponse.from_orm(dataset) for dataset in datasets],
            total=total_count,
            skip=skip,
            limit=limit
        )
        
    except Exception as e:
        logger.error("Dataset listing failed", error=str(e))
        raise HTTPException(status_code=500, detail="Failed to list datasets")


@router.get("/{dataset_id}", response_model=DatasetResponse)
async def get_dataset(
    dataset_id: str,
    current_user: User = Depends(get_current_user),
    cache_manager: CacheManager = Depends(get_cache_manager),
    db: AsyncSession = Depends(get_db)
):
    """Get dataset by ID"""
    
    try:
        # Try cache first
        cached_data = await cache_manager.get_dataset_metadata(dataset_id)
        if cached_data:
            # Verify user has access
            if (cached_data.get("visibility") == "private" and 
                cached_data.get("owner_id") != str(current_user.id) and
                not current_user.is_superuser):
                raise HTTPException(status_code=404, detail="Dataset not found")
            
            # Track access
            await cache_manager.increment_dataset_access(dataset_id)
            return DatasetResponse(**cached_data)
        
        # Fetch from database
        from sqlalchemy import select
        
        query = select(Dataset).where(
            Dataset.id == uuid.UUID(dataset_id),
            Dataset.deleted_at.is_(None)
        )
        
        result = await db.execute(query)
        dataset = result.scalar_one_or_none()
        
        if not dataset:
            raise HTTPException(status_code=404, detail="Dataset not found")
        
        # Check access permissions
        if (dataset.visibility == "private" and 
            dataset.owner_id != current_user.id and
            not current_user.is_superuser):
            raise HTTPException(status_code=404, detail="Dataset not found")
        
        # Cache the result
        await cache_manager.cache_dataset_metadata(
            dataset_id,
            {
                "id": str(dataset.id),
                "name": dataset.name,
                "description": dataset.description,
                "owner_id": str(dataset.owner_id),
                "visibility": dataset.visibility,
                "status": dataset.status,
                "created_at": dataset.created_at.isoformat(),
                "updated_at": dataset.updated_at.isoformat(),
                "datalad_id": dataset.datalad_id,
                "file_count": dataset.file_count,
                "total_size_bytes": dataset.total_size_bytes
            }
        )
        
        # Track access
        await cache_manager.increment_dataset_access(dataset_id)
        
        return DatasetResponse.from_orm(dataset)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get dataset", dataset_id=dataset_id, error=str(e))
        raise HTTPException(status_code=500, detail="Failed to retrieve dataset")


@router.put("/{dataset_id}", response_model=DatasetResponse)
async def update_dataset(
    dataset_id: str,
    dataset_update: DatasetUpdate,
    current_user: User = Depends(get_current_user),
    cache_manager: CacheManager = Depends(get_cache_manager),
    db: AsyncSession = Depends(get_db)
):
    """Update dataset metadata"""
    
    try:
        from sqlalchemy import select
        
        # Fetch dataset
        query = select(Dataset).where(
            Dataset.id == uuid.UUID(dataset_id),
            Dataset.deleted_at.is_(None)
        )
        
        result = await db.execute(query)
        dataset = result.scalar_one_or_none()
        
        if not dataset:
            raise HTTPException(status_code=404, detail="Dataset not found")
        
        # Check permissions
        if dataset.owner_id != current_user.id and not current_user.is_superuser:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        
        # Update fields
        update_data = dataset_update.dict(exclude_unset=True)
        for field, value in update_data.items():
            setattr(dataset, field, value)
        
        await db.commit()
        await db.refresh(dataset)
        
        # Invalidate cache
        await cache_manager.invalidate_dataset_cache(dataset_id)
        
        logger.info("Dataset updated", dataset_id=dataset_id)
        
        return DatasetResponse.from_orm(dataset)
        
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error("Dataset update failed", dataset_id=dataset_id, error=str(e))
        raise HTTPException(status_code=500, detail="Failed to update dataset")


@router.delete("/{dataset_id}")
async def delete_dataset(
    dataset_id: str,
    current_user: User = Depends(get_current_user),
    datalad_service: DataLadService = Depends(get_datalad_service),
    cache_manager: CacheManager = Depends(get_cache_manager),
    db: AsyncSession = Depends(get_db)
):
    """Delete dataset (soft delete)"""
    
    try:
        from sqlalchemy import select
        from datetime import datetime
        
        # Fetch dataset
        query = select(Dataset).where(
            Dataset.id == uuid.UUID(dataset_id),
            Dataset.deleted_at.is_(None)
        )
        
        result = await db.execute(query)
        dataset = result.scalar_one_or_none()
        
        if not dataset:
            raise HTTPException(status_code=404, detail="Dataset not found")
        
        # Check permissions
        if dataset.owner_id != current_user.id and not current_user.is_superuser:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        
        # Soft delete
        dataset.deleted_at = datetime.utcnow()
        
        await db.commit()
        
        # Cleanup DataLad repository (async)
        try:
            await datalad_service.cleanup_dataset(dataset.datalad_id)
        except Exception as e:
            logger.warning("DataLad cleanup failed", dataset_id=dataset_id, error=str(e))
        
        # Invalidate cache
        await cache_manager.invalidate_dataset_cache(dataset_id)
        
        logger.info("Dataset deleted", dataset_id=dataset_id)
        
        return {"message": "Dataset deleted successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error("Dataset deletion failed", dataset_id=dataset_id, error=str(e))
        raise HTTPException(status_code=500, detail="Failed to delete dataset")


@router.post("/{dataset_id}/versions", response_model=DatasetVersionResponse)
async def create_dataset_version(
    dataset_id: str,
    version_data: DatasetVersionCreate,
    current_user: User = Depends(get_current_user),
    datalad_service: DataLadService = Depends(get_datalad_service),
    db: AsyncSession = Depends(get_db)
):
    """Create new dataset version"""
    
    try:
        from sqlalchemy import select
        
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
        
        # Create version in DataLad
        datalad_result = await datalad_service.create_version(
            dataset_id=dataset.datalad_id,
            version_name=version_data.version_name,
            description=version_data.message
        )
        
        # Create database record
        db_version = DatasetVersion(
            dataset_id=dataset.id,
            version_name=version_data.version_name,
            commit_hash=datalad_result["commit_hash"],
            created_by=current_user.id,
            message=version_data.message
        )
        
        db.add(db_version)
        await db.commit()
        await db.refresh(db_version)
        
        logger.info("Dataset version created", 
                   dataset_id=dataset_id, version=version_data.version_name)
        
        return DatasetVersionResponse.from_orm(db_version)
        
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error("Version creation failed", 
                    dataset_id=dataset_id, error=str(e))
        raise HTTPException(status_code=500, detail="Failed to create version")


@router.get("/{dataset_id}/versions", response_model=List[DatasetVersionResponse])
async def list_dataset_versions(
    dataset_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """List all versions of a dataset"""
    
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
        
        # Get versions
        versions_query = select(DatasetVersion).where(
            DatasetVersion.dataset_id == uuid.UUID(dataset_id)
        ).order_by(DatasetVersion.created_at.desc())
        
        result = await db.execute(versions_query)
        versions = result.scalars().all()
        
        return [DatasetVersionResponse.from_orm(version) for version in versions]
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to list versions", dataset_id=dataset_id, error=str(e))
        raise HTTPException(status_code=500, detail="Failed to list versions")