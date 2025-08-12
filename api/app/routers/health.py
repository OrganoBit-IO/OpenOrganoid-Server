from fastapi import APIRouter, Depends
from typing import Dict, Any
import structlog

from app.services.cache_manager import CacheManager
from app.services.file_manager import FileManagementService
from app.main import get_cache_manager, get_file_manager

logger = structlog.get_logger()
router = APIRouter()


@router.get("/health", response_model=Dict[str, Any])
async def health_check():
    """Basic health check endpoint"""
    return {
        "status": "healthy",
        "service": "OpenOrganoid Data Repository API",
        "version": "1.0.0"
    }


@router.get("/health/detailed", response_model=Dict[str, Any])
async def detailed_health_check(
    cache_manager: CacheManager = Depends(get_cache_manager),
    file_manager: FileManagementService = Depends(get_file_manager)
):
    """Detailed health check including service dependencies"""
    
    health_status = {
        "status": "healthy",
        "timestamp": "2024-01-01T00:00:00Z",  # Will be replaced with actual timestamp
        "services": {}
    }
    
    try:
        # Check cache service
        cache_health = await cache_manager.health_check()
        health_status["services"]["cache"] = cache_health
        
        # Check file storage service
        file_health = await file_manager.health_check()
        health_status["services"]["file_storage"] = file_health
        
        # Determine overall status
        service_statuses = [
            cache_health.get("status", "unhealthy"),
            file_health.get("status", "unhealthy")
        ]
        
        if any(status == "unhealthy" for status in service_statuses):
            health_status["status"] = "unhealthy"
        elif any(status == "degraded" for status in service_statuses):
            health_status["status"] = "degraded"
            
    except Exception as e:
        logger.error("Health check failed", error=str(e))
        health_status["status"] = "unhealthy"
        health_status["error"] = str(e)
    
    return health_status


@router.get("/ready")
async def readiness_check():
    """Kubernetes readiness probe endpoint"""
    return {"status": "ready"}


@router.get("/live")
async def liveness_check():
    """Kubernetes liveness probe endpoint"""
    return {"status": "alive"}