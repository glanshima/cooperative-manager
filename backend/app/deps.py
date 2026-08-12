import uuid

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from . import models
from .auth import decode_access_token
from .database import get_db

# tokenUrl is just for the OpenAPI docs UI; the actual login endpoint is
# POST /api/auth/login as defined in routers/auth.py
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)


def get_current_user(
    token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)
) -> models.User:
    credentials_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    if not token:
        raise credentials_error

    payload = decode_access_token(token)
    if not payload:
        raise credentials_error

    user_id = payload.get("sub")
    if not user_id:
        raise credentials_error

    user = db.query(models.User).filter(models.User.id == uuid.UUID(user_id)).first()
    if not user or not user.is_active:
        raise credentials_error

    return user


def require_admin(current_user: models.User = Depends(get_current_user)) -> models.User:
    if current_user.role != models.UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Admin access required")
    return current_user


def require_member(current_user: models.User = Depends(get_current_user)) -> models.User:
    if current_user.role != models.UserRole.MEMBER:
        raise HTTPException(status_code=403, detail="Member access required")
    return current_user


def require_password_already_changed(
    current_user: models.User = Depends(get_current_user),
) -> models.User:
    """
    Use this on any route that shouldn't be reachable until a member has
    completed their forced first-login password reset. The login endpoint
    itself and the change-password endpoint are exempt, obviously.
    """
    if current_user.must_change_password:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You must change your password before continuing.",
        )
    return current_user
