"""In-app notification producers.

Call these from the SAME transaction as the state change they announce --
add the row before the commit that persists the change, never after. A
notification is part of the business outcome ("your loan was approved"),
so it must roll back with it; email is the opposite (sent after commit,
because a mail outage must not undo a review).

Recipient resolution never guesses: a member only has an in-app notice
if a role='member' login exists for them, and an inactive account is
skipped because it cannot sign in to read one.
"""

from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from . import models


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
