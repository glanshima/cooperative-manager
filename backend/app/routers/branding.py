from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db

router = APIRouter(prefix="/api/branding", tags=["branding"])


@router.get("", response_model=schemas.BrandingOut)
def get_branding(db: Session = Depends(get_db)):
    """Unauthenticated by design: the login and password-reset screens must
    wear the cooperative's identity before any user is known. Only the
    public branding slice is exposed -- never module flags, fees or other
    settings, and this read never creates a settings row."""
    settings = db.query(models.Settings).first()
    if settings is None:
        return schemas.BrandingOut(
            cooperative_name=models.DEFAULT_COOPERATIVE_NAME,
            cooperative_short_name=models.DEFAULT_COOPERATIVE_SHORT_NAME,
            cooperative_monogram=models.DEFAULT_COOPERATIVE_MONOGRAM,
            logo_url=None,
        )
    return settings
