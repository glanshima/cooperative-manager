from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from .. import dashboard, models, schemas
from ..database import get_db
from ..deps import require_admin, user_permission_codes

router = APIRouter(prefix="/api/admin/dashboard", tags=["admin-dashboard"])


@router.get("", response_model=schemas.AdminDashboardOut)
def get_admin_dashboard(
    period: str = Query("this_month", pattern="^(this_month|last_month|this_year|last_year)$"),
    current_user: models.User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """One aggregate for the admin landing page. Sections the caller may
    not see are omitted (null) rather than zeroed, so a restricted officer
    cannot tell a real zero from a hidden figure."""
    return dashboard.build_dashboard(db, user_permission_codes(db, current_user), period)
