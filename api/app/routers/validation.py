from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Dict, Any
import uuid
import structlog

from app.database.connection import get_db
from app.database.models import Dataset, DatasetVersion, User
from app.core.security import get_current_user

logger = structlog.get_logger()
router = APIRouter(prefix="/validation")


@router.post("/datasets/{dataset_id}/validate")
async def validate_dataset(
    dataset_id: str,
    validation_config: Dict[str, Any] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Trigger dataset validation"""
    
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
        
        # TODO: Implement actual validation logic
        # This would typically trigger a background task
        
        logger.info("Dataset validation triggered", dataset_id=dataset_id)
        
        return {
            "message": "Validation started",
            "dataset_id": dataset_id,
            "status": "pending"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Validation trigger failed", dataset_id=dataset_id, error=str(e))
        raise HTTPException(status_code=500, detail="Failed to start validation")


@router.get("/datasets/{dataset_id}/status")
async def get_validation_status(
    dataset_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get dataset validation status"""
    
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
        
        # Get latest version validation status
        version_query = select(DatasetVersion).where(
            DatasetVersion.dataset_id == uuid.UUID(dataset_id)
        ).order_by(DatasetVersion.created_at.desc())
        
        result = await db.execute(version_query)
        latest_version = result.first()
        
        if latest_version:
            return {
                "dataset_id": dataset_id,
                "version_id": str(latest_version.id),
                "validation_status": latest_version.validation_status,
                "validation_results": latest_version.validation_results
            }
        else:
            return {
                "dataset_id": dataset_id,
                "validation_status": "no_versions",
                "validation_results": {}
            }
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get validation status", 
                    dataset_id=dataset_id, error=str(e))
        raise HTTPException(status_code=500, detail="Failed to get validation status")