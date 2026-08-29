import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from .. import models, schemas, audit_service
from ..account_lifecycle import (
    is_locked_out,
    record_failed_login,
    record_successful_login,
    validate_password_strength,
)
from ..auth import hash_password, verify_password, create_access_token
from ..database import get_db
from ..deps import get_current_user, require_admin

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=schemas.LoginResponse)
def login(payload: schemas.LoginRequest, request: Request, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.username == payload.username).first()

    invalid = HTTPException(status_code=401, detail="Invalid username or password")

    if not user:
        # Don't leak whether the username exists; still record the
        # attempt for abuse monitoring, without an actor_user_id.
        audit_service.log_event(
            db,
            actor=None,
            actor_username_override=payload.username,
            event_type="auth.login_failed",
            action="login",
            reason="unknown username",
            request=request,
        )
        raise invalid

    if is_locked_out(user):
        audit_service.log_event(
            db,
            actor=user,
            event_type="auth.login_blocked_lockout",
            action="login",
            reason="account temporarily locked after repeated failed attempts",
            request=request,
        )
        raise HTTPException(
            status_code=423,
            detail="This account is temporarily locked due to repeated failed login attempts. Try again later.",
        )

    if not user.is_active or user.account_status != models.AccountStatus.ACTIVE:
        audit_service.log_event(
            db,
            actor=user,
            event_type="auth.login_blocked_inactive",
            action="login",
            reason=f"account_status={user.account_status.value}",
            request=request,
        )
        raise invalid

    if not verify_password(payload.password, user.password_hash):
        record_failed_login(db, user)
        audit_service.log_event(
            db,
            actor=user,
            event_type="auth.login_failed",
            action="login",
            reason="incorrect password",
            request=request,
        )
        raise invalid

    record_successful_login(db, user)

    token, jti, expires_at = create_access_token(user_id=str(user.id), role=user.role.value)
    ip = request.client.host if request.client else None
    session = models.AuthSession(
        jti=jti,
        user_id=user.id,
        expires_at=expires_at,
        ip_address=ip,
        user_agent=request.headers.get("user-agent"),
    )
    db.add(session)
    db.commit()

    audit_service.log_event(
        db, actor=user, event_type="auth.login_succeeded", action="login", request=request
    )

    return schemas.LoginResponse(
        access_token=token,
        role=user.role,
        must_change_password=user.must_change_password,
    )


@router.post("/logout", status_code=204)
def logout(
    request: Request,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Revokes the session behind the current access token so it can no
    longer be used, even though the underlying JWT hasn't expired yet."""
    auth_header = request.headers.get("authorization", "")
    token = auth_header.split(" ", 1)[1] if auth_header.lower().startswith("bearer ") else None
    from ..auth import decode_access_token

    payload = decode_access_token(token) if token else None
    jti = payload.get("jti") if payload else None

    if jti:
        session = db.query(models.AuthSession).filter(models.AuthSession.jti == jti).first()
        if session and session.revoked_at is None:
            session.revoked_at = datetime.utcnow()
            session.revoked_reason = "logout"
            db.commit()

    audit_service.log_event(
        db, actor=current_user, event_type="auth.logout", action="logout", request=request
    )
    return None


@router.post("/change-password", response_model=schemas.UserOut)
def change_password(
    payload: schemas.ChangePasswordRequest,
    request: Request,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not verify_password(payload.current_password, current_user.password_hash):
        raise HTTPException(status_code=401, detail="Current password is incorrect")

    error = validate_password_strength(payload.new_password)
    if error:
        raise HTTPException(status_code=400, detail=error)

    current_user.password_hash = hash_password(payload.new_password)
    current_user.must_change_password = False
    db.commit()
    db.refresh(current_user)

    audit_service.log_event(
        db,
        actor=current_user,
        event_type="auth.password_changed",
        action="update",
        entity_type="user",
        entity_id=str(current_user.id),
        request=request,
    )
    return current_user


@router.get("/me", response_model=schemas.UserOut)
def get_me(current_user: models.User = Depends(get_current_user)):
    return current_user


@router.post("/create-member-login", response_model=schemas.UserOut, status_code=201)
def create_member_login(
    payload: schemas.CreateMemberLoginRequest,
    request: Request,
    current_user: models.User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    member = db.query(models.Member).filter(models.Member.id == payload.member_id).first()
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")

    # Login State Reconciliation Addendum: scoped to role == MEMBER
    # specifically. An admin-role account can independently hold this
    # same member_id (see self_conflict.py / Controlled Remediation
    # Section 1 -- an EXCO officer's admin account and their own
    # self-service member login are two separate User rows that may both
    # legitimately reference the same member_id). Without this role
    # filter, a member who already has an admin account linked to them
    # would be incorrectly blocked from ever getting their own
    # self-service PSN login.
    existing = (
        db.query(models.User)
        .filter(models.User.member_id == member.id, models.User.role == models.UserRole.MEMBER)
        .first()
    )
    if existing:
        raise HTTPException(status_code=409, detail="This member already has a login")

    error = validate_password_strength(payload.temporary_password)
    if error:
        raise HTTPException(status_code=400, detail=error)

    user = models.User(
        username=member.psn,
        password_hash=hash_password(payload.temporary_password),
        role=models.UserRole.MEMBER,
        member_id=member.id,
        must_change_password=True,
        account_status=models.AccountStatus.ACTIVE,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    audit_service.log_event(
        db,
        actor=current_user,
        event_type="auth.member_login_created",
        action="create",
        entity_type="user",
        entity_id=str(user.id),
        new_values={"username": user.username, "member_id": str(member.id)},
        request=request,
    )
    return user


@router.post("/reset-member-password", response_model=schemas.UserOut)
def reset_member_password(
    payload: schemas.CreateMemberLoginRequest,
    request: Request,
    current_user: models.User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Admin resets an existing member's password (e.g. they forgot it),
    setting must_change_password again so the next login forces a reset."""
    user = db.query(models.User).filter(
        models.User.member_id == payload.member_id, models.User.role == models.UserRole.MEMBER
    ).first()
    if not user:
        raise HTTPException(status_code=404, detail="This member doesn't have a login yet")

    error = validate_password_strength(payload.temporary_password)
    if error:
        raise HTTPException(status_code=400, detail=error)

    user.password_hash = hash_password(payload.temporary_password)
    user.must_change_password = True
    # A password reset is also a reasonable moment to clear any lockout,
    # since the admin has just verified the member's identity out of band.
    user.failed_login_count = 0
    user.locked_until = None
    db.commit()
    db.refresh(user)

    audit_service.log_event(
        db,
        actor=current_user,
        event_type="auth.member_password_reset",
        action="update",
        entity_type="user",
        entity_id=str(user.id),
        request=request,
    )
    return user
