"""Initial migration

Revision ID: 5d1c9df3f701
Revises: 
Create Date: 2025-07-26 06:11:49.932005

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '5d1c9df3f701'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Create extensions
    op.execute("CREATE EXTENSION IF NOT EXISTS \"uuid-ossp\"")
    op.execute("CREATE EXTENSION IF NOT EXISTS \"pg_trgm\"")
    
    # Create users table
    op.create_table(
        'users',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('email', sa.String(255), nullable=False),
        sa.Column('username', sa.String(100), nullable=False),
        sa.Column('password_hash', sa.String(255), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('is_superuser', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index('ix_users_email', 'users', ['email'], unique=True)
    op.create_index('ix_users_username', 'users', ['username'], unique=True)
    
    # Create datasets table
    op.create_table(
        'datasets',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('title', sa.String(500), nullable=False),
        sa.Column('description', sa.Text()),
        sa.Column('owner_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('visibility', sa.String(20), nullable=False, server_default='private'),
        sa.Column('status', sa.String(20), nullable=False, server_default='draft'),
        sa.Column('current_version', sa.String(50), nullable=False, server_default='1.0.0'),
        sa.Column('datalad_path', sa.String(1000)),
        sa.Column('storage_path', sa.String(1000)),
        sa.Column('total_size_bytes', sa.BigInteger(), nullable=False, server_default='0'),
        sa.Column('file_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('data_schema', postgresql.JSONB()),
        sa.Column('statistical_summary', postgresql.JSONB()),
        sa.Column('feature_metadata', postgresql.JSONB()),
        sa.Column('ml_ready', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('search_vector', postgresql.TSVECTOR()),
    )
    op.create_index('ix_datasets_search_vector', 'datasets', ['search_vector'], postgresql_using='gin')
    op.create_index('ix_datasets_owner_visibility', 'datasets', ['owner_id', 'visibility'])
    op.create_index('ix_datasets_status', 'datasets', ['status'])
    
    # Create dataset_versions table
    op.create_table(
        'dataset_versions',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('dataset_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('datasets.id'), nullable=False),
        sa.Column('version', sa.String(50), nullable=False),
        sa.Column('commit_hash', sa.String(64)),
        sa.Column('changelog', sa.Text()),
        sa.Column('created_by', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('is_current', sa.Boolean(), nullable=False, server_default=sa.text('false')),
    )
    op.create_index('ix_dataset_version_unique', 'dataset_versions', ['dataset_id', 'version'], unique=True)
    op.create_index('ix_dataset_version_current', 'dataset_versions', ['dataset_id', 'is_current'])
    
    # Create dataset_files table
    op.create_table(
        'dataset_files',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('dataset_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('datasets.id'), nullable=False),
        sa.Column('version_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('dataset_versions.id'), nullable=False),
        sa.Column('file_path', sa.String(1000), nullable=False),
        sa.Column('file_name', sa.String(255), nullable=False),
        sa.Column('file_size_bytes', sa.BigInteger(), nullable=False),
        sa.Column('content_type', sa.String(100)),
        sa.Column('checksum_md5', sa.String(32)),
        sa.Column('checksum_sha256', sa.String(64)),
        sa.Column('status', sa.String(20), nullable=False, server_default='uploaded'),
        sa.Column('validation_results', postgresql.JSONB()),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index('ix_dataset_file_unique', 'dataset_files', ['dataset_id', 'version_id', 'file_path'], unique=True)
    op.create_index('ix_dataset_file_status', 'dataset_files', ['status'])
    op.create_index('ix_dataset_file_content_type', 'dataset_files', ['content_type'])
    
    # Create api_keys table
    op.create_table(
        'api_keys',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('key_hash', sa.String(255), nullable=False),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('permissions', postgresql.JSONB()),
        sa.Column('last_used_at', sa.DateTime()),
        sa.Column('expires_at', sa.DateTime()),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index('ix_api_key_hash', 'api_keys', ['key_hash'], unique=True)
    op.create_index('ix_api_key_user_active', 'api_keys', ['user_id', 'is_active'])
    
    # Create validation_rules table
    op.create_table(
        'validation_rules',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('description', sa.Text()),
        sa.Column('rule_type', sa.String(50), nullable=False),
        sa.Column('configuration', postgresql.JSONB()),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index('ix_validation_rule_type', 'validation_rules', ['rule_type'])
    op.create_index('ix_validation_rule_active', 'validation_rules', ['is_active'])
    
    # Create dataset_permissions table
    op.create_table(
        'dataset_permissions',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('dataset_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('datasets.id'), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('permission_type', sa.String(20), nullable=False),
        sa.Column('granted_by', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('granted_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index('ix_dataset_permission_unique', 'dataset_permissions', ['dataset_id', 'user_id'], unique=True)
    op.create_index('ix_dataset_permission_type', 'dataset_permissions', ['permission_type'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('dataset_permissions')
    op.drop_table('validation_rules')
    op.drop_table('api_keys')
    op.drop_table('dataset_files')
    op.drop_table('dataset_versions')
    op.drop_table('datasets')
    op.drop_table('users')
