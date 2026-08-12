from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..deps import get_current_user, require_admin

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
    current_user: models.User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    settings = _get_or_create_settings(db)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(settings, field, value)
    db.commit()
    db.refresh(settings)
    return settings
