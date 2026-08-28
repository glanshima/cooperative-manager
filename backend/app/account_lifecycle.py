"""
Account lifecycle + password-policy + lockout helpers (Phase 1, Sections
6-7). Centralized here so every place that changes a user's status,
records a login attempt, or validates a password does it the same way.
"""
import os
import re
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from . import models

MAX_FAILED_LOGIN_ATTEMPTS = int(os.getenv("MAX_FAILED_LOGIN_ATTEMPTS", "5"))
LOCKOUT_MINUTES = int(os.getenv("LOCKOUT_MINUTES", "15"))
PASSWORD_MIN_LENGTH = int(os.getenv("PASSWORD_MIN_LENGTH", "8"))


def validate_password_strength(password: str) -> Optional[str]:
    """Returns an error message if the password fails policy, else None."""
    if len(password) < PASSWORD_MIN_LENGTH:
        return f"Password must be at least {PASSWORD_MIN_LENGTH} characters"
    if not re.search(r"[A-Za-z]", password):
        return "Password must contain at least one letter"
    if not re.search(r"[0-9]", password):
        return "Password must contain at least one number"
    return None


def is_locked_out(user: models.User) -> bool:
    return bool(user.locked_until and user.locked_until > datetime.utcnow())


def record_failed_login(db: Session, user: models.User) -> None:
    user.failed_login_count = (user.failed_login_count or 0) + 1
    user.last_failed_login_at = datetime.utcnow()
    if user.failed_login_count >= MAX_FAILED_LOGIN_ATTEMPTS:
        user.locked_until = datetime.utcnow() + timedelta(minutes=LOCKOUT_MINUTES)
    db.commit()


def record_successful_login(db: Session, user: models.User) -> None:
    user.failed_login_count = 0
    user.locked_until = None
    user.last_login_at = datetime.utcnow()
    db.commit()


def set_account_status(
    db: Session,
    user: models.User,
    status: models.AccountStatus,
    *,
    changed_by: Optional[models.User],
    reason: Optional[str] = None,
) -> None:
    """The single place that transitions account_status, keeping the
    legacy is_active flag mirrored to it. A DEACTIVATED or SUSPENDED
    admin loses authority on their very next request, since
    get_current_user re-checks account_status on every call -- there is
    no cached/stale authorization state to worry about."""
    user.account_status = status
    user.is_active = status == models.AccountStatus.ACTIVE
    user.status_reason = reason
    user.status_changed_at = datetime.utcnow()
    user.status_changed_by_user_id = changed_by.id if changed_by else None
    db.commit()
