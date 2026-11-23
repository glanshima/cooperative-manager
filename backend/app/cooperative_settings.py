"""Access to the cooperative's settings row.

Each deployment runs its own database, so the single settings row *is* the
cooperative -- there is no tenant column to filter on. Values are read per
request rather than cached (see models.Settings), so a policy change
applies to the very next request.
"""
from decimal import Decimal

from sqlalchemy.orm import Session

from . import models

ZERO = Decimal("0.00")


def get_or_create(db: Session) -> models.Settings:
    """Create the default row on first access instead of requiring a
    separate seed step."""
    settings = db.query(models.Settings).first()
    if settings is None:
        settings = models.Settings()
        db.add(settings)
        db.commit()
        db.refresh(settings)
    return settings


def minimum_monthly_contribution(db: Session) -> Decimal:
    """The cooperative's contribution floor; 0 means no floor."""
    return get_or_create(db).minimum_monthly_contribution or ZERO
