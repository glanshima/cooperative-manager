from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .. import schemas
from ..cooperative_branding import current_brand
from ..database import get_db

router = APIRouter(prefix="/api/branding", tags=["branding"])


@router.get("", response_model=schemas.BrandingOut)
def get_branding(db: Session = Depends(get_db)):
    """Unauthenticated by design: the login and password-reset screens must
    wear the cooperative's identity before any user is known. Only the
    public branding slice is exposed -- never module flags, fees or other
    settings, and this read never creates a settings row."""
    brand = current_brand(db)
    return schemas.BrandingOut(
        cooperative_name=brand.name,
        cooperative_short_name=brand.short_name,
        cooperative_monogram=brand.monogram,
        logo_url=brand.logo_url,
    )
