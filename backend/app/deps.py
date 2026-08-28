import uuid
from datetime import datetime

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from . import models
from .auth import decode_access_token
from .database import get_db

# tokenUrl is just for the OpenAPI docs UI; the actual login endpoint is
# POST /api/auth/login as defined in routers/auth.py
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)


def get_current_user(
    request: Request,
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
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
    jti = payload.get("jti")
    if not user_id:
        raise credentials_error

    user = db.query(models.User).filter(models.User.id == uuid.UUID(user_id)).first()
    if not user:
        raise credentials_error

    # Session-level revocation check (Section 6-7): a token whose session
    # has been explicitly logged out/revoked is rejected even though the
    # JWT signature itself is still valid and unexpired. Tokens issued
    # before this Phase 1 change carry no jti and have no session row --
    # they're honored until they naturally expire (bounded by
    # ACCESS_TOKEN_EXPIRE_MINUTES) rather than force-logging out every
    # already-logged-in user the moment this deploys.
    if jti:
        session = db.query(models.AuthSession).filter(models.AuthSession.jti == jti).first()
        if session is not None and session.revoked_at is not None:
            raise credentials_error

    # Account-status is the authoritative lifecycle check (Section 7): a
    # deactivated or suspended account loses access on its very next
    # request, independent of the still-valid JWT. is_active is checked
    # too only for defense-in-depth against any code path that still
    # writes it directly instead of going through account_lifecycle.py.
    if not user.is_active or user.account_status != models.AccountStatus.ACTIVE:
        raise credentials_error

    request.state.current_user = user
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


def user_has_permission(db: Session, user: models.User, code: str) -> bool:
    if user.role != models.UserRole.ADMIN:
        return False
    if user.is_super_admin:
        return True
    return (
        db.query(models.RolePermission)
        .join(models.Role, models.RolePermission.role_id == models.Role.id)
        .join(models.Permission, models.RolePermission.permission_id == models.Permission.id)
        .join(
            models.UserRoleAssignment,
            models.UserRoleAssignment.role_id == models.Role.id,
        )
        .filter(
            models.UserRoleAssignment.user_id == user.id,
            models.UserRoleAssignment.is_active.is_(True),
            models.Role.is_active.is_(True),
            models.Permission.code == code,
        )
        .first()
        is not None
    )


def require_any_permission(*codes: str):
    """
    Dependency factory: require_any_permission("a", "b") returns a
    dependency that 403s unless the current user holds at least one of
    the given permission codes (directly, via an active Office/Role
    assignment, or via is_super_admin).

    Added in the Phase 1 remediation pass (Section 3) specifically for
    endpoints that legitimately serve more than one distinct permission
    -- e.g. GET /api/permissions must be readable by someone who holds
    admin.role_manage (they need the catalogue to render the Roles UI's
    permission matrix) OR admin.permission_manage (the narrower
    catalogue-maintenance permission), without requiring both.
    """

    def _dependency(
        current_user: models.User = Depends(require_admin),
        db: Session = Depends(get_db),
    ) -> models.User:
        if not any(user_has_permission(db, current_user, code) for code in codes):
            raise HTTPException(
                status_code=403,
                detail=(
                    "You do not have any of the required permissions "
                    f"({', '.join(codes)}) for this action."
                ),
            )
        return current_user

    return _dependency


def require_permission(code: str):
    """
    Dependency factory: require_permission("loan.approve") returns a
    FastAPI dependency that 403s unless the current user is an admin-type
    account holding that permission (directly, via an active
    Office/Role/Permission assignment, or via is_super_admin).

    This is layered ON TOP OF the existing role == ADMIN gate rather than
    replacing it, per Phase 1 Section 4 (preserve existing functionality,
    extend rather than replace): every pre-existing admin-only endpoint
    keeps working for accounts migrated to is_super_admin=True (see
    migration notes), while newly created admin accounts must be
    explicitly granted the permission through the Office/Role model.
    """

    def _dependency(
        current_user: models.User = Depends(require_admin),
        db: Session = Depends(get_db),
    ) -> models.User:
        if not user_has_permission(db, current_user, code):
            raise HTTPException(
                status_code=403,
                detail=f"You do not have the '{code}' permission for this action.",
            )
        return current_user

    return _dependency
