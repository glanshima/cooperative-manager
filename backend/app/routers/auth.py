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

    # Revoke all OTHER active sessions for this user (preserving current session)
    auth_header = request.headers.get("authorization", "")
    token = auth_header.split(" ", 1)[1] if auth_header.lower().startswith("bearer ") else None
    from ..auth import decode_access_token
    payload_jwt = decode_access_token(token) if token else None
    current_jti = payload_jwt.get("jti") if payload_jwt else None

    for session in db.query(models.AuthSession).filter(
        models.AuthSession.user_id == current_user.id,
        models.AuthSession.revoked_at.is_(None),
        models.AuthSession.jti != current_jti,
    ):
        session.revoked_at = datetime.utcnow()
        session.revoked_reason = "password_changed"

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


# ---------------------------------------------------------------------------
# Self-Service Password Recovery (Forgot Password / Reset Password)
# ---------------------------------------------------------------------------

import hashlib
import os
import secrets
from datetime import timedelta
from ..email_utils import password_reset_email_html, send_email

PASSWORD_RESET_TOKEN_EXPIRE_MINUTES = int(os.getenv("PASSWORD_RESET_TOKEN_EXPIRE_MINUTES", "15"))
APP_URL = os.getenv("APP_URL", "http://localhost:3000")
MAX_RECOVERY_REQUESTS_PER_WINDOW = int(os.getenv("MAX_RECOVERY_REQUESTS_PER_WINDOW", "3"))


def _hash_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.strip().encode("utf-8")).hexdigest()


def _resolve_user_and_email_for_recovery(db: Session, identifier: str):
    """
    Resolves the target User and their recovery email/name.
    Matches username (case-insensitive), PSN, or member email.
    """
    clean_id = identifier.strip()
    if not clean_id:
        return None, None, None

    # 1. Exact or case-insensitive match on User.username
    user = (
        db.query(models.User)
        .filter(models.User.username.ilike(clean_id))
        .first()
    )

    # 2. If not found and clean_id contains '@', check Member.email
    if not user and "@" in clean_id:
        member = (
            db.query(models.Member)
            .filter(models.Member.email.ilike(clean_id))
            .first()
        )
        if member:
            user = member.get_member_login_user(db) or member.get_admin_login_user(db)

    # 3. If not found, check Member.psn
    if not user:
        member = (
            db.query(models.Member)
            .filter(models.Member.psn.ilike(clean_id))
            .first()
        )
        if member:
            user = member.get_member_login_user(db) or member.get_admin_login_user(db)

    if not user:
        return None, None, None

    # Resolve email and display name
    email = None
    name = user.username
    if user.member_id:
        member = db.query(models.Member).filter(models.Member.id == user.member_id).first()
        if member and member.email:
            email = member.email
            name = member.name
    elif "@" in user.username:
        email = user.username
        name = user.username

    return user, email, name


@router.post("/forgot-password", response_model=schemas.GenericMessageResponse)
def forgot_password(
    payload: schemas.ForgotPasswordRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Initiates self-service password recovery.
    Always returns a generic success response to prevent account enumeration.
    """
    generic_msg = (
        "If an account matching the provided identifier exists, password reset "
        "instructions have been sent to the associated email address."
    )
    ip = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")

    user, email, name = _resolve_user_and_email_for_recovery(db, payload.identifier)

    # Account enumeration defense: if user not found, non-active, or has no email,
    # log event and return identical generic message.
    if not user or user.account_status != models.AccountStatus.ACTIVE or not email:
        audit_service.log_event(
            db,
            actor=None,
            actor_username_override=payload.identifier,
            event_type="auth.recovery_requested_unknown",
            action="request_recovery",
            reason="unknown or un-recoverable account identifier",
            request=request,
        )
        return schemas.GenericMessageResponse(message=generic_msg)

    # Rate limiting: max N requests per 15 minutes per user
    window_start = datetime.utcnow() - timedelta(minutes=PASSWORD_RESET_TOKEN_EXPIRE_MINUTES)
    recent_count = (
        db.query(models.PasswordResetToken)
        .filter(
            models.PasswordResetToken.user_id == user.id,
            models.PasswordResetToken.created_at >= window_start,
        )
        .count()
    )
    if recent_count >= MAX_RECOVERY_REQUESTS_PER_WINDOW:
        audit_service.log_event(
            db,
            actor=user,
            event_type="auth.recovery_rate_limited",
            action="request_recovery",
            entity_type="user",
            entity_id=str(user.id),
            reason="Rate limit exceeded for recovery requests",
            request=request,
        )
        return schemas.GenericMessageResponse(message=generic_msg)

    # Generate high-entropy 256-bit token
    raw_token = secrets.token_urlsafe(32)
    token_hash = _hash_token(raw_token)
    expires_at = datetime.utcnow() + timedelta(minutes=PASSWORD_RESET_TOKEN_EXPIRE_MINUTES)

    reset_token_record = models.PasswordResetToken(
        user_id=user.id,
        token_hash=token_hash,
        expires_at=expires_at,
        attempt_count=0,
        ip_address=ip,
        user_agent=user_agent,
    )
    db.add(reset_token_record)
    db.commit()

    # Send reset link (raw token is only passed in the email URL, never stored in DB or logs)
    reset_url = f"{APP_URL.rstrip('/')}/reset-password?token={raw_token}"
    email_html = password_reset_email_html(
        recipient_name=name,
        reset_url=reset_url,
        expires_minutes=PASSWORD_RESET_TOKEN_EXPIRE_MINUTES,
    )
    send_email(to=email, subject="Password Reset Request - MACT Cooperative", html=email_html)

    audit_service.log_event(
        db,
        actor=user,
        event_type="auth.recovery_requested",
        action="request_recovery",
        entity_type="user",
        entity_id=str(user.id),
        request=request,
    )
    return schemas.GenericMessageResponse(message=generic_msg)


@router.post("/verify-reset-token")
def verify_reset_token(payload: schemas.VerifyResetTokenRequest, db: Session = Depends(get_db)):
    """
    Pre-validates a recovery token for the frontend without consuming it.
    """
    token_hash = _hash_token(payload.token)
    token_record = (
        db.query(models.PasswordResetToken)
        .filter(models.PasswordResetToken.token_hash == token_hash)
        .first()
    )
    if not token_record or token_record.used_at is not None:
        raise HTTPException(
            status_code=400,
            detail="This password reset link is invalid or has already been used.",
        )
    if token_record.expires_at <= datetime.utcnow():
        raise HTTPException(
            status_code=400,
            detail="This password reset link has expired. Please request a new one.",
        )
    if token_record.attempt_count >= 5:
        raise HTTPException(
            status_code=400,
            detail="Too many attempts on this link. Please request a new password reset.",
        )
    return {"valid": True}


@router.post("/reset-password", response_model=schemas.GenericMessageResponse)
def reset_password(
    payload: schemas.ResetPasswordRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Consumes a valid recovery token atomically and updates the user's password.
    Revokes all active sessions for the user and clears login lockouts.
    """
    error = validate_password_strength(payload.new_password)
    if error:
        raise HTTPException(status_code=400, detail=error)

    token_hash = _hash_token(payload.token)

    # Concurrency / replay protection: Row lock on the token record
    token_record = (
        db.query(models.PasswordResetToken)
        .filter(models.PasswordResetToken.token_hash == token_hash)
        .with_for_update()
        .first()
    )

    if not token_record:
        audit_service.log_event(
            db,
            actor=None,
            event_type="auth.recovery_failed",
            action="reset_password",
            reason="unknown token hash",
            request=request,
        )
        raise HTTPException(
            status_code=400,
            detail="This password reset link is invalid or has already been used.",
        )

    # Check attempt limit
    if token_record.attempt_count >= 5:
        audit_service.log_event(
            db,
            actor=token_record.user,
            event_type="auth.recovery_failed",
            action="reset_password",
            reason="token attempt limit exceeded",
            request=request,
        )
        raise HTTPException(
            status_code=400,
            detail="Too many attempts on this link. Please request a new password reset.",
        )

    # Check single-use
    if token_record.used_at is not None:
        token_record.attempt_count += 1
        db.commit()
        audit_service.log_event(
            db,
            actor=token_record.user,
            event_type="auth.recovery_failed",
            action="reset_password",
            reason="token already used",
            request=request,
        )
        raise HTTPException(
            status_code=400,
            detail="This password reset link has already been used.",
        )

    # Check expiry
    if token_record.expires_at <= datetime.utcnow():
        token_record.attempt_count += 1
        db.commit()
        audit_service.log_event(
            db,
            actor=token_record.user,
            event_type="auth.recovery_failed",
            action="reset_password",
            reason="token expired",
            request=request,
        )
        raise HTTPException(
            status_code=400,
            detail="This password reset link has expired. Please request a new one.",
        )

    # Resolve user
    user = (
        db.query(models.User)
        .filter(models.User.id == token_record.user_id)
        .with_for_update()
        .first()
    )
    if not user:
        raise HTTPException(status_code=404, detail="User account not found.")

    if user.account_status in (models.AccountStatus.SUSPENDED, models.AccountStatus.DEACTIVATED):
        audit_service.log_event(
            db,
            actor=user,
            event_type="auth.recovery_blocked_inactive",
            action="reset_password",
            reason=f"account_status={user.account_status.value}",
            request=request,
        )
        raise HTTPException(
            status_code=403,
            detail="This account is currently suspended or deactivated. Contact an administrator.",
        )

    # Apply password reset
    user.password_hash = hash_password(payload.new_password)
    user.must_change_password = False
    user.failed_login_count = 0
    user.locked_until = None

    # Consume current token
    token_record.used_at = datetime.utcnow()

    # Invalidate all other pending recovery tokens for this user
    for other_token in (
        db.query(models.PasswordResetToken)
        .filter(
            models.PasswordResetToken.user_id == user.id,
            models.PasswordResetToken.id != token_record.id,
            models.PasswordResetToken.used_at.is_(None),
        )
        .all()
    ):
        other_token.used_at = datetime.utcnow()

    # Revoke all active sessions for this user
    active_sessions = (
        db.query(models.AuthSession)
        .filter(models.AuthSession.user_id == user.id, models.AuthSession.revoked_at.is_(None))
        .all()
    )
    for session in active_sessions:
        session.revoked_at = datetime.utcnow()
        session.revoked_reason = "password_recovery"

    db.commit()
    db.refresh(user)

    audit_service.log_event(
        db,
        actor=user,
        event_type="auth.password_recovered",
        action="reset_password",
        entity_type="user",
        entity_id=str(user.id),
        request=request,
    )

    return schemas.GenericMessageResponse(
        message="Password has been successfully reset. You can now log in."
    )
