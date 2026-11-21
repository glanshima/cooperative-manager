"""In-app notification producers.

Call these from the SAME transaction as the state change they announce --
add the row before the commit that persists the change, never after. A
notification is part of the business outcome ("your loan was approved"),
so it must roll back with it; email is the opposite (sent after commit,
because a mail outage must not undo a review).

Recipient resolution never guesses: a member only has an in-app notice
if a role='member' login exists for them, and an inactive account is
skipped because it cannot sign in to read one. Staff notices go to the
holders of the permission that lets them act on the thing being
announced, never to "all admins".
"""

from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from . import models

# Categories whose email the account holder may switch off. Account and
# system notices are deliberate security communications and have no
# preference at all.
OPTIONAL_EMAIL_CATEGORIES = (
    models.NotificationCategory.LOAN,
    models.NotificationCategory.REPAYMENT,
)


def notify(
    db: Session,
    *,
    user_id,
    category: models.NotificationCategory,
    title: str,
    body: Optional[str] = None,
    link_path: Optional[str] = None,
) -> Optional[models.Notification]:
    """Queues a notification; the caller commits it with its own change."""
    if user_id is None:
        return None
    notification = models.Notification(
        user_id=user_id,
        category=category,
        title=title,
        body=body,
        link_path=link_path,
    )
    db.add(notification)
    return notification


def notify_member(
    db: Session,
    member: models.Member,
    *,
    category: models.NotificationCategory,
    title: str,
    body: Optional[str] = None,
    link_path: Optional[str] = None,
) -> Optional[models.Notification]:
    """Notifies the member's self-service login, when one exists."""
    user = member.get_member_login_user(db)
    if user is None or not user.is_active:
        return None
    return notify(
        db,
        user_id=user.id,
        category=category,
        title=title,
        body=body,
        link_path=link_path,
    )


def notify_staff(
    db: Session,
    *,
    permission_code: str,
    category: models.NotificationCategory,
    title: str,
    body: Optional[str] = None,
    link_path: Optional[str] = None,
) -> int:
    """Queues one notice per active admin who can act on the permission.

    The permission dependency is imported here to keep this module free
    of FastAPI wiring at import time (routers import both modules).
    """
    from .deps import user_has_permission

    recipients = (
        db.query(models.User)
        .filter(
            models.User.role == models.UserRole.ADMIN,
            models.User.is_active.is_(True),
        )
        .all()
    )
    queued = 0
    for user in recipients:
        if user_has_permission(db, user, permission_code):
            notify(
                db,
                user_id=user.id,
                category=category,
                title=title,
                body=body,
                link_path=link_path,
            )
            queued += 1
    return queued


def member_allows_email(
    db: Session, member: models.Member, category: models.NotificationCategory
) -> bool:
    """Whether the member's own login left this category's email switched on."""
    if category not in OPTIONAL_EMAIL_CATEGORIES:
        return True
    user = member.get_member_login_user(db)
    if user is None:
        return True
    preference = (
        db.query(models.NotificationPreference)
        .filter(models.NotificationPreference.user_id == user.id)
        .first()
    )
    if preference is None:
        return True
    if category == models.NotificationCategory.LOAN:
        return preference.email_loan
    return preference.email_repayment

