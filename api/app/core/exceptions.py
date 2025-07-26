from typing import Any, Optional

from fastapi import HTTPException, status


class OpenOrganoidException(Exception):
    """Base exception class for OpenOrganoid Server."""
    
    def __init__(self, message: str, details: Optional[dict] = None):
        self.message = message
        self.details = details or {}
        super().__init__(self.message)


class AuthenticationError(OpenOrganoidException):
    """Raised when authentication fails."""
    pass


class AuthorizationError(OpenOrganoidException):
    """Raised when user lacks permission for an action."""
    pass


class ValidationError(OpenOrganoidException):
    """Raised when data validation fails."""
    pass


class DatasetError(OpenOrganoidException):
    """Raised when dataset operations fail."""
    pass


class FileError(OpenOrganoidException):
    """Raised when file operations fail."""
    pass


class DataLadError(OpenOrganoidException):
    """Raised when DataLad operations fail."""
    pass


# HTTP Exception helpers
def credentials_exception() -> HTTPException:
    """Create a credentials exception."""
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )


def insufficient_permissions_exception() -> HTTPException:
    """Create an insufficient permissions exception."""
    return HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Insufficient permissions",
    )


def not_found_exception(resource: str = "Resource") -> HTTPException:
    """Create a not found exception."""
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"{resource} not found",
    )


def conflict_exception(message: str = "Resource already exists") -> HTTPException:
    """Create a conflict exception."""
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=message,
    )


def validation_exception(message: str, details: Optional[dict] = None) -> HTTPException:
    """Create a validation exception."""
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail={"message": message, "details": details or {}},
    )


def internal_server_exception(message: str = "Internal server error") -> HTTPException:
    """Create an internal server error exception."""
    return HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail=message,
    )