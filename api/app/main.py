from contextlib import asynccontextmanager
from typing import AsyncGenerator
import logging
import asyncio
from pathlib import Path

from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from prometheus_fastapi_instrumentator import Instrumentator
import structlog

from app.config import settings
from app.database.connection import create_tables, close_db_connection
from app.core.exceptions import setup_exception_handlers
from app.services.datalad_service import DataLadService
from app.services.cache_manager import CacheManager
from app.services.file_manager import FileManagementService

# Import routers
from app.routers.auth import router as auth_router
from app.routers.datasets import router as datasets_router
from app.routers.files import router as files_router
from app.routers.validation import router as validation_router
from app.routers.admin import router as admin_router
from app.routers.health import router as health_router

# Configure structured logging
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.processors.JSONRenderer()
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger()

# Global service instances
datalad_service: DataLadService = None
cache_manager: CacheManager = None
file_manager: FileManagementService = None


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan manager for startup and shutdown tasks"""
    
    # Startup
    logger.info("Starting OpenOrganoid Server", version=settings.app_version)
    
    try:
        # Initialize services
        global datalad_service, cache_manager, file_manager
        
        # Create data directories
        Path(settings.datalad_path).mkdir(parents=True, exist_ok=True)
        Path(settings.storage_path).mkdir(parents=True, exist_ok=True)
        Path(settings.upload_path).mkdir(parents=True, exist_ok=True)
        
        # Initialize database tables (optional - may fail in development)
        try:
            await create_tables()
            logger.info("Database tables initialized")
        except Exception as e:
            logger.warning("Database initialization failed - continuing without DB", error=str(e))
        
        # Initialize DataLad service (optional)
        try:
            datalad_service = DataLadService(workspace_root=Path(settings.datalad_path))
            await datalad_service.initialize()
            logger.info("DataLad service initialized")
        except Exception as e:
            logger.warning("DataLad service initialization failed - continuing without DataLad", error=str(e))
        
        # Initialize cache manager (optional)
        try:
            cache_manager = CacheManager(redis_url=settings.redis_url)
            await cache_manager.initialize()
            logger.info("Cache manager initialized")
        except Exception as e:
            logger.warning("Cache manager initialization failed - continuing without Redis", error=str(e))
        
        # Initialize file management service (optional)
        try:
            file_manager = FileManagementService({
                'endpoint_url': getattr(settings, 's3_endpoint_url', None),
                'access_key_id': getattr(settings, 's3_access_key_id', None),
                'secret_access_key': getattr(settings, 's3_secret_access_key', None),
                'bucket_name': getattr(settings, 's3_bucket_name', None),
                'region': getattr(settings, 's3_region', 'us-east-1')
            })
            await file_manager.initialize()
            logger.info("File management service initialized")
        except Exception as e:
            logger.warning("File management service initialization failed - continuing without S3", error=str(e))
        
        # Warm cache if available
        try:
            await warm_metadata_cache()
            logger.info("Cache warmed with frequently accessed data")
        except Exception as e:
            logger.warning("Cache warming failed", error=str(e))
        
        logger.info("Application startup completed successfully")
        
    except Exception as e:
        logger.error("Critical error during startup", error=str(e))
        # Don't raise - allow app to start for health checks
    
    yield
    
    # Shutdown
    logger.info("Shutting down OpenOrganoid Server")
    
    try:
        # Cleanup services
        if file_manager:
            await file_manager.cleanup()
        if cache_manager:
            await cache_manager.cleanup()
        if datalad_service:
            await datalad_service.cleanup()
        
        # Close database connections
        await close_db_connection()
        
        logger.info("Application shutdown completed successfully")
        
    except Exception as e:
        logger.error("Error during shutdown", error=str(e))


async def warm_metadata_cache():
    """Warm cache with frequently accessed datasets"""
    # This would typically query for popular/recent datasets and cache their metadata
    # Implementation depends on usage analytics
    pass


# Create FastAPI application
app = FastAPI(
    title="OpenOrganoid Data Repository API",
    description="Advanced dataset management with DataLad version control and S3 storage",
    version=settings.app_version,
    lifespan=lifespan,
    docs_url="/docs" if settings.environment == "development" else None,
    redoc_url="/redoc" if settings.environment == "development" else None
)

# Setup exception handlers
setup_exception_handlers(app)

# Add security middleware
app.add_middleware(
    TrustedHostMiddleware, 
    allowed_hosts=["*"] if settings.environment == "development" else ["*.railway.app"]
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add prometheus metrics if in production
if settings.environment == "production":
    instrumentator = Instrumentator()
    instrumentator.instrument(app).expose(app)

# Include routers
app.include_router(health_router, tags=["health"])
app.include_router(auth_router, prefix=settings.api_v1_prefix, tags=["authentication"])
app.include_router(datasets_router, prefix=settings.api_v1_prefix, tags=["datasets"])
app.include_router(files_router, prefix=settings.api_v1_prefix, tags=["files"])
app.include_router(validation_router, prefix=settings.api_v1_prefix, tags=["validation"])
app.include_router(admin_router, prefix=settings.api_v1_prefix, tags=["admin"])

# Root endpoint
@app.get("/")
async def root():
    return {
        "message": "OpenOrganoid Data Repository API",
        "version": settings.app_version,
        "environment": settings.environment,
        "docs": "/docs" if settings.environment == "development" else "Contact admin for API documentation"
    }

# Dependency providers for services
def get_datalad_service() -> DataLadService:
    if datalad_service is None:
        raise HTTPException(status_code=503, detail="DataLad service not initialized")
    return datalad_service

def get_cache_manager() -> CacheManager:
    if cache_manager is None:
        raise HTTPException(status_code=503, detail="Cache manager not initialized")
    return cache_manager

def get_file_manager() -> FileManagementService:
    if file_manager is None:
        raise HTTPException(status_code=503, detail="File management service not initialized")
    return file_manager