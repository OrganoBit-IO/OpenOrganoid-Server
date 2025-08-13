from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, Dict, Any, List
from datetime import datetime
import uuid


class DatasetCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255, description="Dataset name")
    description: Optional[str] = Field(None, description="Dataset description")
    organization_id: Optional[uuid.UUID] = Field(None, description="Organization ID if applicable")
    visibility: str = Field("private", description="Dataset visibility (private, public, organization)")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Additional metadata")


class DatasetUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    visibility: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class DatasetResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    id: uuid.UUID
    name: str
    description: Optional[str]
    owner_id: uuid.UUID
    organization_id: Optional[uuid.UUID]
    visibility: str
    status: str
    datalad_id: str
    s3_prefix: Optional[str]
    current_version: Optional[str]
    total_size_bytes: int
    file_count: int
    created_at: datetime
    updated_at: datetime
    metadata: Dict[str, Any]


class DatasetListResponse(BaseModel):
    datasets: List[DatasetResponse]
    total: int
    skip: int
    limit: int


class DatasetVersionCreate(BaseModel):
    version_name: str = Field(..., min_length=1, max_length=100)
    message: Optional[str] = Field(None, description="Version commit message")


class DatasetVersionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    id: uuid.UUID
    dataset_id: uuid.UUID
    version_name: str
    commit_hash: str
    parent_version_id: Optional[uuid.UUID]
    created_by: uuid.UUID
    created_at: datetime
    message: Optional[str]
    file_count: int
    total_size: int
    validation_status: str
    validation_results: Dict[str, Any]


class DatasetFileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    id: uuid.UUID
    dataset_id: uuid.UUID
    version_id: uuid.UUID
    file_path: str
    s3_key: Optional[str]
    file_size: Optional[int]
    checksum: Optional[str]
    mime_type: Optional[str]
    created_at: datetime