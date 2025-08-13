from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Dict, Any, List
import structlog

from app.database.connection import get_db
from app.database.models import User, Dataset
from app.core.security import get_current_user
from app.services.cache_manager import CacheManager
from app.main import get_cache_manager

logger = structlog.get_logger()
router = APIRouter(prefix="/admin")


def require_admin(current_user: User = Depends(get_current_user)):
    """Dependency to require admin privileges"""
    if not current_user.is_superuser:
        raise HTTPException(status_code=403, detail="Admin privileges required")
    return current_user


@router.get("/stats")
async def get_system_stats(
    admin_user: User = Depends(require_admin),
    cache_manager: CacheManager = Depends(get_cache_manager),
    db: AsyncSession = Depends(get_db)
):
    """Get system statistics"""
    
    try:
        from sqlalchemy import select, func
        
        # Get user count
        user_count_query = select(func.count(User.id)).where(User.is_active == True)
        user_result = await db.execute(user_count_query)
        user_count = user_result.scalar()
        
        # Get dataset count
        dataset_count_query = select(func.count(Dataset.id)).where(Dataset.deleted_at.is_(None))
        dataset_result = await db.execute(dataset_count_query)
        dataset_count = dataset_result.scalar()
        
        # Get popular datasets
        popular_datasets = await cache_manager.get_popular_datasets(limit=5)
        
        return {
            "users": {
                "total": user_count,
                "active": user_count  # Simplified
            },
            "datasets": {
                "total": dataset_count,
                "public": 0,  # TODO: Calculate
                "private": 0  # TODO: Calculate
            },
            "popular_datasets": popular_datasets,
            "cache_status": await cache_manager.health_check()
        }
        
    except Exception as e:
        logger.error("Failed to get system stats", error=str(e))
        raise HTTPException(status_code=500, detail="Failed to get system statistics")


@router.post("/cache/clear")
async def clear_cache(
    admin_user: User = Depends(require_admin),
    cache_manager: CacheManager = Depends(get_cache_manager)
):
    """Clear system cache"""
    
    try:
        # Clear all cache data
        await cache_manager.redis.flushdb()
        
        logger.info("System cache cleared", admin_user=str(admin_user.id))
        
        return {"message": "Cache cleared successfully"}
        
    except Exception as e:
        logger.error("Failed to clear cache", error=str(e))
        raise HTTPException(status_code=500, detail="Failed to clear cache")


@router.get("/users")
async def list_users(
    admin_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """List all users (admin only)"""
    
    try:
        from sqlalchemy import select
        
        query = select(User).order_by(User.created_at.desc())
        result = await db.execute(query)
        users = result.scalars().all()
        
        return [
            {
                "id": str(user.id),
                "username": user.username,
                "email": user.email,
                "is_active": user.is_active,
                "is_superuser": user.is_superuser,
                "created_at": user.created_at.isoformat()
            }
            for user in users
        ]
        
    except Exception as e:
        logger.error("Failed to list users", error=str(e))
        raise HTTPException(status_code=500, detail="Failed to list users")