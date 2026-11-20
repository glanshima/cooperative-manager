"""In-app notifications.

Every route is hard-scoped to the signed-in account: the user id comes
from the token, never from the request, so a notification id alone can
never read or mark another user's row (marking an unowned id is a 404,
not a permission hint).
"""

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..deps import get_current_user

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


def _scope(current_user: models.User):
    return models.Notification.user_id == current_user.id


@router.get("", response_model=schemas.NotificationPageOut)
def list_notifications(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Newest first, with the totals the bell needs to render its badge."""
    base = db.query(models.Notification).filter(_scope(current_user))
    total = base.count()
    unread_count = base.filter(models.Notification.is_read.is_(False)).count()
    items = (
        base.order_by(models.Notification.created_at.desc(), models.Notification.id.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    return schemas.NotificationPageOut(
        items=[schemas.NotificationOut.model_validate(item) for item in items],
        total=total,
        unread_count=unread_count,
    )


@router.post("/read-all", response_model=schemas.NotificationReadAllOut)
def mark_all_read(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    updated = (
        db.query(models.Notification)
        .filter(_scope(current_user), models.Notification.is_read.is_(False))
        .update(
            {models.Notification.is_read: True, models.Notification.read_at: datetime.utcnow()},
            synchronize_session=False,
        )
    )
    db.commit()
    return schemas.NotificationReadAllOut(updated=updated)


@router.post("/{notification_id}/read", response_model=schemas.NotificationOut)
def mark_read(
    notification_id: uuid.UUID,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    notification = (
        db.query(models.Notification)
        .filter(_scope(current_user), models.Notification.id == notification_id)
        .first()
    )
    if notification is None:
        raise HTTPException(status_code=404, detail="Notification not found")

    if not notification.is_read:
        notification.is_read = True
        notification.read_at = datetime.utcnow()
        db.commit()
        db.refresh(notification)
    return notification
