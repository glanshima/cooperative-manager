from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from .. import models, schemas, audit_service
from ..database import get_db
from ..deps import get_current_user, require_permission

router = APIRouter(prefix="/api/settings", tags=["settings"])


def _get_or_create_settings(db: Session) -> models.Settings:
    """Single-row table -- create the default row on first access if it
    doesn't exist yet, rather than requiring a separate seed step."""
    settings = db.query(models.Settings).first()
    if not settings:
        settings = models.Settings()
        db.add(settings)
        db.commit()
        db.refresh(settings)
    return settings


@router.get("", response_model=schemas.SettingsOut)
def get_settings(
    current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """Any authenticated user can read settings -- members need to see
    the loan form fee before applying, for instance."""
    return _get_or_create_settings(db)


@router.put("", response_model=schemas.SettingsOut)
def update_settings(
    payload: schemas.SettingsUpdate,
    request: Request,
    current_user: models.User = Depends(require_permission("admin.settings_manage")),
    db: Session = Depends(get_db),
):
    settings = _get_or_create_settings(db)
    changes = payload.model_dump(exclude_unset=True)
    previous = {field: getattr(settings, field) for field in changes}
    for field, value in changes.items():
        setattr(settings, field, value)
    db.commit()
    db.refresh(settings)

    audit_service.log_event(
        db,
        actor=current_user,
        event_type="settings.updated",
        action="update",
        entity_type="settings",
        entity_id=str(settings.id) if hasattr(settings, "id") else "settings",
        previous_values=previous,
        new_values=changes,
        request=request,
    )
    return settings
