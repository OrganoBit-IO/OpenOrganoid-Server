from datetime import datetime, timedelta
from typing import Optional
from uuid import UUID

from sqlalchemy.orm import Session

from ..core.exceptions import AuthenticationError, AuthorizationError, ValidationError
from ..core.security import (
    create_access_token,
    create_refresh_token,
    generate_api_key,
    get_password_hash,
    hash_api_key,
    verify_password,
    verify_token,
    verify_api_key,
    create_password_reset_token,
    verify_password_reset_token,
)
from ..database.models import User, ApiKey
from ..schemas.auth import (
    UserCreate,
    UserUpdate,
    Token,
    ApiKeyCreate,
    ApiKeyResponse,
    ApiKeyUpdate,
)


class AuthService:
    """Service for authentication and authorization operations."""
    
    def __init__(self, db: Session):
        self.db = db
    
    def get_user_by_email(self, email: str) -> Optional[User]:
        """Get user by email address."""
        return self.db.query(User).filter(User.email == email).first()
    
    def get_user_by_username(self, username: str) -> Optional[User]:
        """Get user by username."""
        return self.db.query(User).filter(User.username == username).first()
    
    def get_user_by_id(self, user_id: UUID) -> Optional[User]:
        """Get user by ID."""
        return self.db.query(User).filter(User.id == user_id).first()
    
    def create_user(self, user_data: UserCreate) -> User:
        """Create a new user."""
        # Check if user already exists
        if self.get_user_by_email(user_data.email):
            raise ValidationError("Email already registered")
        
        if self.get_user_by_username(user_data.username):
            raise ValidationError("Username already taken")
        
        # Create user
        hashed_password = get_password_hash(user_data.password)
        db_user = User(
            email=user_data.email,
            username=user_data.username,
            password_hash=hashed_password,
            is_active=user_data.is_active,
            is_superuser=user_data.is_superuser,
        )
        
        self.db.add(db_user)
        self.db.commit()
        self.db.refresh(db_user)
        
        return db_user
    
    def authenticate_user(self, email: str, password: str) -> Optional[User]:
        """Authenticate user with email and password."""
        user = self.get_user_by_email(email)
        if not user:
            return None
        
        if not user.is_active:
            raise AuthenticationError("User account is inactive")
        
        if not verify_password(password, user.password_hash):
            return None
        
        return user
    
    def create_tokens_for_user(self, user: User) -> Token:
        """Create access and refresh tokens for user."""
        token_data = {
            "sub": str(user.id),
            "email": user.email,
            "username": user.username,
        }
        
        access_token = create_access_token(token_data)
        refresh_token = create_refresh_token(token_data)
        
        return Token(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=1800,  # 30 minutes
        )
    
    def verify_access_token(self, token: str) -> Optional[User]:
        """Verify access token and return user."""
        payload = verify_token(token)
        if not payload:
            return None
        
        user_id = payload.get("sub")
        if not user_id:
            return None
        
        try:
            user_uuid = UUID(user_id)
            user = self.get_user_by_id(user_uuid)
            if not user or not user.is_active:
                return None
            return user
        except (ValueError, TypeError):
            return None
    
    def refresh_access_token(self, refresh_token: str) -> Optional[Token]:
        """Create new access token from refresh token."""
        payload = verify_token(refresh_token)
        if not payload:
            return None
        
        if payload.get("type") != "refresh":
            return None
        
        user_id = payload.get("sub")
        if not user_id:
            return None
        
        try:
            user_uuid = UUID(user_id)
            user = self.get_user_by_id(user_uuid)
            if not user or not user.is_active:
                return None
            
            return self.create_tokens_for_user(user)
        except (ValueError, TypeError):
            return None
    
    def update_user(self, user_id: UUID, user_data: UserUpdate) -> Optional[User]:
        """Update user information."""
        user = self.get_user_by_id(user_id)
        if not user:
            return None
        
        # Check for email/username conflicts
        if user_data.email and user_data.email != user.email:
            if self.get_user_by_email(user_data.email):
                raise ValidationError("Email already registered")
        
        if user_data.username and user_data.username != user.username:
            if self.get_user_by_username(user_data.username):
                raise ValidationError("Username already taken")
        
        # Update user fields
        for field, value in user_data.dict(exclude_unset=True).items():
            setattr(user, field, value)
        
        user.updated_at = datetime.utcnow()
        self.db.commit()
        self.db.refresh(user)
        
        return user
    
    def change_password(self, user_id: UUID, current_password: str, new_password: str) -> bool:
        """Change user password."""
        user = self.get_user_by_id(user_id)
        if not user:
            return False
        
        if not verify_password(current_password, user.password_hash):
            raise AuthenticationError("Current password is incorrect")
        
        user.password_hash = get_password_hash(new_password)
        user.updated_at = datetime.utcnow()
        self.db.commit()
        
        return True
    
    def create_password_reset_token_for_email(self, email: str) -> Optional[str]:
        """Create password reset token for email."""
        user = self.get_user_by_email(email)
        if not user:
            return None
        
        return create_password_reset_token(email)
    
    def reset_password_with_token(self, token: str, new_password: str) -> bool:
        """Reset password using reset token."""
        email = verify_password_reset_token(token)
        if not email:
            return False
        
        user = self.get_user_by_email(email)
        if not user:
            return False
        
        user.password_hash = get_password_hash(new_password)
        user.updated_at = datetime.utcnow()
        self.db.commit()
        
        return True
    
    def create_api_key(self, user_id: UUID, api_key_data: ApiKeyCreate) -> ApiKeyResponse:
        """Create a new API key for user."""
        user = self.get_user_by_id(user_id)
        if not user:
            raise ValidationError("User not found")
        
        # Generate API key
        api_key = generate_api_key()
        key_hash = hash_api_key(api_key)
        
        # Create API key record
        db_api_key = ApiKey(
            user_id=user_id,
            key_hash=key_hash,
            name=api_key_data.name,
            permissions=api_key_data.permissions,
            expires_at=api_key_data.expires_at,
        )
        
        self.db.add(db_api_key)
        self.db.commit()
        self.db.refresh(db_api_key)
        
        return ApiKeyResponse(
            id=db_api_key.id,
            key=api_key,
            name=db_api_key.name,
            permissions=db_api_key.permissions or [],
            expires_at=db_api_key.expires_at,
        )
    
    def verify_api_key(self, api_key: str) -> Optional[User]:
        """Verify API key and return associated user."""
        key_hash = hash_api_key(api_key)
        
        db_api_key = self.db.query(ApiKey).filter(
            ApiKey.key_hash == key_hash,
            ApiKey.is_active == True
        ).first()
        
        if not db_api_key:
            return None
        
        # Check expiration
        if db_api_key.expires_at and db_api_key.expires_at < datetime.utcnow():
            return None
        
        # Update last used
        db_api_key.last_used_at = datetime.utcnow()
        self.db.commit()
        
        # Get associated user
        user = self.get_user_by_id(db_api_key.user_id)
        if not user or not user.is_active:
            return None
        
        return user
    
    def get_user_api_keys(self, user_id: UUID) -> list[ApiKey]:
        """Get all API keys for a user."""
        return self.db.query(ApiKey).filter(ApiKey.user_id == user_id).all()
    
    def update_api_key(self, api_key_id: UUID, user_id: UUID, api_key_data: ApiKeyUpdate) -> Optional[ApiKey]:
        """Update an API key."""
        db_api_key = self.db.query(ApiKey).filter(
            ApiKey.id == api_key_id,
            ApiKey.user_id == user_id
        ).first()
        
        if not db_api_key:
            return None
        
        # Update fields
        for field, value in api_key_data.dict(exclude_unset=True).items():
            setattr(db_api_key, field, value)
        
        self.db.commit()
        self.db.refresh(db_api_key)
        
        return db_api_key
    
    def delete_api_key(self, api_key_id: UUID, user_id: UUID) -> bool:
        """Delete an API key."""
        db_api_key = self.db.query(ApiKey).filter(
            ApiKey.id == api_key_id,
            ApiKey.user_id == user_id
        ).first()
        
        if not db_api_key:
            return False
        
        self.db.delete(db_api_key)
        self.db.commit()
        
        return True