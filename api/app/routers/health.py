from fastapi import APIRouter
from typing import Dict, Any
import structlog

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
async def detailed_health_check():
    """Detailed health check - simplified to avoid circular imports"""
    
    # For now, return basic status
    # TODO: Add proper service checks after resolving circular imports
    health_status = {
        "status": "healthy",
        "timestamp": "2024-01-01T00:00:00Z",
        "services": {
            "note": "Service checks temporarily disabled to avoid circular imports"
        }
    }
    
    return health_status


@router.get("/ready")
async def readiness_check():
    """Kubernetes readiness probe endpoint"""
    return {"status": "ready"}


@router.get("/live")
async def liveness_check():
    """Kubernetes liveness probe endpoint"""
    return {"status": "alive"}