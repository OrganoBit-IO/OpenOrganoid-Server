from typing import Optional
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")
    
    # Database Configuration
    database_url: str = Field(
        default="postgresql://openorganoid:openorganoid_dev_password@localhost:5432/openorganoid",
        description="PostgreSQL database connection URL"
    )
    
    # Redis Configuration
    redis_url: str = Field(
        default="redis://localhost:6379/0",
        description="Redis connection URL for caching and message queue"
    )
    
    # Security Configuration
    secret_key: str = Field(
        default="dev_secret_key_change_in_production",
        description="Secret key for JWT token signing"
    )
    algorithm: str = Field(default="HS256", description="JWT algorithm")
    access_token_expire_minutes: int = Field(default=30, description="JWT token expiration time")
    
    # Application Configuration
    app_name: str = Field(default="OpenOrganoid Server", description="Application name")
    app_version: str = Field(default="1.0.0", description="Application version")
    environment: str = Field(default="development", description="Environment (development, production)")
    debug: bool = Field(default=True, description="Debug mode")
    
    # File Storage Configuration
    storage_path: str = Field(default="./data/storage", description="Base path for file storage")
    upload_path: str = Field(default="./data/uploads", description="Path for temporary uploads")
    max_file_size: int = Field(default=100 * 1024 * 1024 * 1024, description="Max file size in bytes (100GB)")
    
    # DataLad Configuration
    datalad_path: str = Field(default="./data/datalad", description="Base path for DataLad repositories")
    
    # S3/DigitalOcean Spaces Configuration
    s3_endpoint_url: Optional[str] = Field(default=None, description="S3 endpoint URL (for DigitalOcean Spaces)")
    s3_access_key_id: Optional[str] = Field(default=None, description="S3 access key ID")
    s3_secret_access_key: Optional[str] = Field(default=None, description="S3 secret access key")
    s3_bucket_name: Optional[str] = Field(default=None, description="S3 bucket name")
    s3_region: str = Field(default="us-east-1", description="S3 region")
    
    # Railway Configuration
    railway_environment: Optional[str] = Field(default=None, description="Railway environment")
    port: int = Field(default=8000, description="Server port")
    
    # API Configuration
    api_v1_prefix: str = Field(default="/api/v1", description="API v1 prefix")
    cors_origins: list[str] = Field(
        default=["http://localhost:3000", "http://localhost:8080"],
        description="CORS allowed origins"
    )
    
    # Pagination
    default_page_size: int = Field(default=20, description="Default pagination page size")
    max_page_size: int = Field(default=100, description="Maximum pagination page size")
    
    # Celery Configuration
    celery_broker_url: Optional[str] = Field(default=None, description="Celery broker URL")
    celery_result_backend: Optional[str] = Field(default=None, description="Celery result backend URL")
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Set Celery URLs to Redis URL if not explicitly provided
        if self.celery_broker_url is None:
            self.celery_broker_url = self.redis_url
        if self.celery_result_backend is None:
            self.celery_result_backend = self.redis_url


settings = Settings()