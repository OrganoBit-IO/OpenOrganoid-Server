import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    BigInteger,
    Index,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB, TSVECTOR
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from .connection import Base


class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), unique=True, nullable=False, index=True)
    username = Column(String(100), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    is_superuser = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    datasets = relationship("Dataset", back_populates="owner")
    api_keys = relationship("ApiKey", back_populates="user")
    dataset_permissions = relationship("DatasetPermission", back_populates="user")
    created_versions = relationship("DatasetVersion", back_populates="created_by_user")

    def __repr__(self):
        return f"<User(id={self.id}, username={self.username}, email={self.email})>"


class Organization(Base):
    __tablename__ = "organizations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    description = Column(Text)
    slug = Column(String(100), unique=True, nullable=False, index=True)
    owner_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)
    settings = Column(JSONB, default=lambda: {})

    # Relationships
    owner = relationship("User")
    datasets = relationship("Dataset", back_populates="organization")
    memberships = relationship("OrganizationMembership", back_populates="organization")

    def __repr__(self):
        return f"<Organization(id={self.id}, name={self.name}, slug={self.slug})>"


class OrganizationMembership(Base):
    __tablename__ = "organization_memberships"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    role = Column(String(20), default="member", nullable=False)  # owner, admin, member
    joined_at = Column(DateTime, default=func.now(), nullable=False)

    # Relationships
    organization = relationship("Organization", back_populates="memberships")
    user = relationship("User")

    # Unique constraint
    __table_args__ = (
        Index("ix_org_membership_unique", organization_id, user_id, unique=True),
        Index("ix_org_membership_role", role),
    )

    def __repr__(self):
        return f"<OrganizationMembership(org_id={self.organization_id}, user_id={self.user_id}, role={self.role})>"


class Dataset(Base):
    __tablename__ = "datasets"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)  # Changed from title to name
    description = Column(Text)
    owner_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"))  # Added organization support
    visibility = Column(String(20), default="private", nullable=False)  # private, public, organization
    status = Column(String(20), default="draft", nullable=False)  # draft, validating, published, archived
    datalad_id = Column(String(255), unique=True, nullable=False)  # DataLad dataset ID
    s3_prefix = Column(String(500))  # S3 storage prefix
    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)
    deleted_at = Column(DateTime)  # Soft deletion support
    metadata = Column(JSONB, default=lambda: {})  # General metadata storage
    
    # Current state
    current_version = Column(String(50))
    total_size_bytes = Column(BigInteger, default=0, nullable=False)
    file_count = Column(Integer, default=0, nullable=False)

    # Full-text search
    search_vector = Column(TSVECTOR)

    # Relationships
    owner = relationship("User", back_populates="datasets")
    organization = relationship("Organization", back_populates="datasets")
    versions = relationship("DatasetVersion", back_populates="dataset", cascade="all, delete-orphan")
    files = relationship("DatasetFile", back_populates="dataset", cascade="all, delete-orphan")
    permissions = relationship("DatasetPermission", back_populates="dataset", cascade="all, delete-orphan")

    # Indexes
    __table_args__ = (
        Index("ix_datasets_search_vector", search_vector, postgresql_using="gin"),
        Index("ix_datasets_owner_visibility", owner_id, visibility),
        Index("ix_datasets_org", organization_id),
        Index("ix_datasets_status", status),
        Index("ix_datasets_created", created_at),
        Index("ix_metadata_gin", metadata, postgresql_using="gin"),
    )

    @hybrid_property
    def current_version_obj(self):
        return next((v for v in self.versions if v.is_current), None)

    def __repr__(self):
        return f"<Dataset(id={self.id}, name={self.name}, owner_id={self.owner_id})>"


class DatasetVersion(Base):
    __tablename__ = "dataset_versions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    dataset_id = Column(UUID(as_uuid=True), ForeignKey("datasets.id"), nullable=False)
    version_name = Column(String(100), nullable=False)
    commit_hash = Column(String(64), nullable=False)
    parent_version_id = Column(UUID(as_uuid=True), ForeignKey("dataset_versions.id"))
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=func.now(), nullable=False)
    message = Column(Text)
    file_count = Column(Integer, default=0)
    total_size = Column(BigInteger, default=0)
    validation_status = Column(String(20), default="pending")  # pending, running, passed, failed
    validation_results = Column(JSONB, default=lambda: {})

    # Relationships
    dataset = relationship("Dataset", back_populates="versions")
    created_by_user = relationship("User", back_populates="created_versions")
    parent_version = relationship("DatasetVersion", remote_side=[id])
    files = relationship("DatasetFile", back_populates="version", cascade="all, delete-orphan")

    # Unique constraint
    __table_args__ = (
        Index("ix_dataset_version_unique", dataset_id, version_name, unique=True),
        Index("ix_versions_dataset", dataset_id),
        Index("ix_versions_hash", commit_hash),
        Index("ix_versions_status", validation_status),
    )

    def __repr__(self):
        return f"<DatasetVersion(id={self.id}, dataset_id={self.dataset_id}, version={self.version_name})>"


class DatasetFile(Base):
    __tablename__ = "dataset_files"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    dataset_id = Column(UUID(as_uuid=True), ForeignKey("datasets.id"), nullable=False)
    version_id = Column(UUID(as_uuid=True), ForeignKey("dataset_versions.id"), nullable=False)
    file_path = Column(String(1000), nullable=False)
    s3_key = Column(String(1000))  # S3 storage key
    file_size = Column(BigInteger)
    checksum = Column(String(128))  # Combined checksum field
    mime_type = Column(String(255))  # Renamed from content_type
    created_at = Column(DateTime, default=func.now(), nullable=False)

    # Relationships
    dataset = relationship("Dataset", back_populates="files")
    version = relationship("DatasetVersion", back_populates="files")

    # Unique constraint and indexes
    __table_args__ = (
        Index("ix_files_dataset_version", dataset_id, version_id),
        Index("ix_files_path", file_path),
        Index("ix_files_s3_key", s3_key),
    )

    def __repr__(self):
        return f"<DatasetFile(id={self.id}, file_path={self.file_path}, dataset_id={self.dataset_id})>"


class ApiKey(Base):
    __tablename__ = "api_keys"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    key_hash = Column(String(255), nullable=False, unique=True)
    name = Column(String(100), nullable=False)
    permissions = Column(JSONB)
    last_used_at = Column(DateTime)
    expires_at = Column(DateTime)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=func.now(), nullable=False)

    # Relationships
    user = relationship("User", back_populates="api_keys")

    # Indexes
    __table_args__ = (
        Index("ix_api_key_hash", key_hash),
        Index("ix_api_key_user_active", user_id, is_active),
    )

    def __repr__(self):
        return f"<ApiKey(id={self.id}, name={self.name}, user_id={self.user_id})>"


class ValidationRule(Base):
    __tablename__ = "validation_rules"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(100), nullable=False)
    description = Column(Text)
    rule_type = Column(String(50), nullable=False)  # file_format, schema, custom
    configuration = Column(JSONB)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=func.now(), nullable=False)

    # Indexes
    __table_args__ = (
        Index("ix_validation_rule_type", rule_type),
        Index("ix_validation_rule_active", is_active),
    )

    def __repr__(self):
        return f"<ValidationRule(id={self.id}, name={self.name}, rule_type={self.rule_type})>"


class DatasetPermission(Base):
    __tablename__ = "dataset_permissions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    dataset_id = Column(UUID(as_uuid=True), ForeignKey("datasets.id"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    permission_type = Column(String(20), nullable=False)  # read, write, admin
    granted_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    granted_at = Column(DateTime, default=func.now(), nullable=False)

    # Relationships
    dataset = relationship("Dataset", back_populates="permissions")
    user = relationship("User", back_populates="dataset_permissions")
    granted_by_user = relationship("User", foreign_keys=[granted_by])

    # Unique constraint
    __table_args__ = (
        Index("ix_dataset_permission_unique", dataset_id, user_id, unique=True),
        Index("ix_dataset_permission_type", permission_type),
    )

    def __repr__(self):
        return f"<DatasetPermission(dataset_id={self.dataset_id}, user_id={self.user_id}, permission={self.permission_type})>"