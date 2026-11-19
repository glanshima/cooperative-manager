"""The cooperative's identity, resolved from its settings row.

One source of fallbacks for every consumer that needs the cooperative's
name outside a database session's lifetime: the public /api/branding
route and the transactional email templates.
"""

from dataclasses import dataclass

from sqlalchemy.orm import Session

from . import models


@dataclass(frozen=True)
class CooperativeBrand:
    name: str
    short_name: str
    monogram: str
    logo_url: str | None = None


DEFAULT_BRAND = CooperativeBrand(
    name=models.DEFAULT_COOPERATIVE_NAME,
    short_name=models.DEFAULT_COOPERATIVE_SHORT_NAME,
    monogram=models.DEFAULT_COOPERATIVE_MONOGRAM,
)


def brand_from_settings(settings: models.Settings | None) -> CooperativeBrand:
    if settings is None:
        return DEFAULT_BRAND
    return CooperativeBrand(
        name=settings.cooperative_name or DEFAULT_BRAND.name,
        short_name=settings.cooperative_short_name or DEFAULT_BRAND.short_name,
        monogram=settings.cooperative_monogram or DEFAULT_BRAND.monogram,
        logo_url=settings.logo_url,
    )


def current_brand(db: Session) -> CooperativeBrand:
    return brand_from_settings(db.query(models.Settings).first())
