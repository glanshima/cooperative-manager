"""Monthly contribution change requests.

Member.monthly_contribution_amount is what payroll deducts. An officer
records it once (bootstrap, while it is still unset -- see
routers/members.py); from then on it only moves through this flow:

  member applies (or an officer applies on their behalf)
    -> pending
    -> approved  amount takes effect from the FIRST OF NEXT MONTH
    -> rejected  nothing changes, the reason is recorded

Approval is deliberately never retroactive and never immediate: the
current payroll month may already be drafted or submitted, and confirmed
deduction lines keep the amount actually deducted, so savings history
(savings.contributions_balance) cannot be rewritten by a later decision.

Deciding a request is a conflict-of-interest sensitive action -- an officer
must not approve their own next of kin's contribution -- so approve/reject
go through require_no_member_conflict, while reading the queue follows the
read policy: visible, flagged, actions blocked.
"""
import uuid
from datetime import date, datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from .. import audit_service, models, schemas
from .. import contributions as contribution_rules
from ..database import get_db
from ..deps import (
    require_module_enabled,
    require_password_already_changed,
    require_permission,
)
from ..self_conflict import (
    get_conflicted_member_ids,
    log_conflicted_view,
    mark_conflicted_reads,
    require_no_member_conflict,
)

router = APIRouter(tags=["contribution-changes"])

# Contribution amounts are member-record administration. The member's own
# self-service endpoints below are deliberately left ungated, exactly like
# GET /api/members/me: they power the member dashboard, not the module's
# administration surface.
_officer_gate = [Depends(require_module_enabled("members"))]

_PENDING_INDEX = "uq_contribution_change_requests_member_pending"


def _fetch(db: Session, request_id: uuid.UUID) -> Optional[models.ContributionChangeRequest]:
    return (
        db.query(models.ContributionChangeRequest)
        .options(joinedload(models.ContributionChangeRequest.member))
        .filter(models.ContributionChangeRequest.id == request_id)
        .first()
    )


def _fetch_locked(db: Session, request_id: uuid.UUID) -> Optional[models.ContributionChangeRequest]:
    # No joined loads here: FOR UPDATE cannot span the outer join a
    # joinedload produces (same constraint documented in
    # routers/payroll_deductions.py).
    return (
        db.query(models.ContributionChangeRequest)
        .filter(models.ContributionChangeRequest.id == request_id)
        .with_for_update()
        .first()
    )


def _audit(
    db: Session,
    actor: models.User,
    row: models.ContributionChangeRequest,
    *,
    event_type: str,
    action: str,
    previous_status: models.ContributionChangeRequestStatus,
    reason: Optional[str] = None,
    extra: Optional[dict] = None,
    request: Optional[Request] = None,
) -> None:
    new_values = {
        "status": row.status.value,
        "member_id": str(row.member_id),
        "current_amount": str(row.current_amount) if row.current_amount is not None else None,
        "requested_amount": str(row.requested_amount),
        "effective_from": row.effective_from.isoformat() if row.effective_from else None,
    }
    if extra:
        new_values.update(extra)
    audit_service.log_event(
        db,
        actor=actor,
        event_type=event_type,
        action=action,
        entity_type="contribution_change_request",
        entity_id=str(row.id),
        previous_values={"status": previous_status.value},
        new_values=new_values,
        reason=reason,
        request=request,
    )


def _create_request(
    db: Session,
    member: models.Member,
    *,
    requested_amount,
    reason: str,
    actor: models.User,
    request: Request,
) -> models.ContributionChangeRequest:
    contribution_rules.assert_may_have_contribution(member)
    if (
        member.monthly_contribution_amount is not None
        and requested_amount == member.monthly_contribution_amount
    ):
        raise HTTPException(
            status_code=400,
            detail="That is already this member's monthly contribution",
        )

    if contribution_rules.pending_request(db, member.id) is not None:
        raise HTTPException(
            status_code=409,
            detail="This member already has a contribution change request awaiting a decision",
        )

    row = models.ContributionChangeRequest(
        member_id=member.id,
        current_amount=member.monthly_contribution_amount,
        requested_amount=requested_amount,
        reason=reason,
        requested_by_user_id=actor.id,
    )
    db.add(row)
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        constraint = getattr(getattr(error.orig, "diag", None), "constraint_name", None)
        if constraint != _PENDING_INDEX:
            raise
        # Two applications raced past the check above; the partial unique
        # index is the guarantee behind it.
        raise HTTPException(
            status_code=409,
            detail="This member already has a contribution change request awaiting a decision",
        )

    row = _fetch(db, row.id)
    _audit(
        db,
        actor,
        row,
        event_type="contribution_change.requested",
        action="create",
        previous_status=models.ContributionChangeRequestStatus.PENDING,
        reason=reason,
        request=request,
    )
    return row


def _own_member(db: Session, current_user: models.User) -> models.Member:
    if current_user.role != models.UserRole.MEMBER or not current_user.member_id:
        raise HTTPException(status_code=403, detail="Only members have a contribution to change")
    member = db.query(models.Member).filter(models.Member.id == current_user.member_id).first()
    if member is None:
        raise HTTPException(status_code=404, detail="Member record not found")
    return member


# ---------------------------------------------------------------------------
# Member self-service
# ---------------------------------------------------------------------------

@router.get(
    "/api/members/me/contribution-change-requests",
    response_model=List[schemas.ContributionChangeRequestOut],
)
def list_my_contribution_requests(
    current_user: models.User = Depends(require_password_already_changed),
    db: Session = Depends(get_db),
):
    member = _own_member(db, current_user)
    return (
        db.query(models.ContributionChangeRequest)
        .filter(models.ContributionChangeRequest.member_id == member.id)
        .order_by(models.ContributionChangeRequest.created_at.desc())
        .all()
    )


@router.post(
    "/api/members/me/contribution-change-requests",
    response_model=schemas.ContributionChangeRequestOut,
    status_code=201,
)
def request_my_contribution_change(
    payload: schemas.ContributionChangeRequestCreate,
    request: Request,
    current_user: models.User = Depends(require_password_already_changed),
    db: Session = Depends(get_db),
):
    """A member acting on their own record is not a conflict of interest --
    the guard exists for officers deciding about someone they are linked
    to, and the decision here still belongs to an unconflicted officer."""
    member = _own_member(db, current_user)
    return _create_request(
        db,
        member,
        requested_amount=payload.requested_amount,
        reason=payload.reason,
        actor=current_user,
        request=request,
    )


# ---------------------------------------------------------------------------
# Officer review
# ---------------------------------------------------------------------------

@router.get(
    "/api/contribution-change-requests",
    response_model=List[schemas.ContributionChangeRequestOut],
    dependencies=_officer_gate,
)
def list_contribution_requests(
    request: Request,
    status: Optional[models.ContributionChangeRequestStatus] = Query(default=None),
    member_id: Optional[uuid.UUID] = Query(default=None),
    current_user: models.User = Depends(require_permission("savings.view")),
    db: Session = Depends(get_db),
):
    query = db.query(models.ContributionChangeRequest).options(
        joinedload(models.ContributionChangeRequest.member)
    )
    if status is not None:
        query = query.filter(models.ContributionChangeRequest.status == status)
    if member_id is not None:
        query = query.filter(models.ContributionChangeRequest.member_id == member_id)

    rows = query.order_by(models.ContributionChangeRequest.created_at.desc()).all()
    items = [schemas.ContributionChangeRequestOut.model_validate(row) for row in rows]
    flagged = mark_conflicted_reads(items, get_conflicted_member_ids(db, current_user))
    log_conflicted_view(
        db,
        current_user,
        conflicted_count=flagged,
        action_description="browsed contribution change requests",
        entity_type="contribution_change_request",
        request=request,
    )
    return items


@router.post(
    "/api/contribution-change-requests",
    response_model=schemas.ContributionChangeRequestOut,
    status_code=201,
    dependencies=_officer_gate,
)
def raise_contribution_request(
    payload: schemas.ContributionChangeRequestOnBehalf,
    request: Request,
    current_user: models.User = Depends(require_permission("savings.request_change")),
    db: Session = Depends(get_db),
):
    """For a member with no login of their own to apply with. The officer
    raising it still cannot decide it themselves if they are conflicted."""
    member = db.query(models.Member).filter(models.Member.id == payload.member_id).first()
    if member is None:
        raise HTTPException(status_code=404, detail="Member not found")

    require_no_member_conflict(
        db,
        current_user,
        member,
        action_description="raise a contribution change request for this member",
        permission_code="savings.request_change",
        entity_type="member",
        entity_id=str(member.id),
        request=request,
    )
    return _create_request(
        db,
        member,
        requested_amount=payload.requested_amount,
        reason=payload.reason,
        actor=current_user,
        request=request,
    )


def _review(
    db: Session,
    current_user: models.User,
    request: Request,
    request_id: uuid.UUID,
    *,
    approve: bool,
    reason: Optional[str],
    permission_code: str,
):
    row = _fetch_locked(db, request_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Contribution change request not found")

    member = (
        db.query(models.Member)
        .filter(models.Member.id == row.member_id)
        .with_for_update()
        .first()
    )
    require_no_member_conflict(
        db,
        current_user,
        member,
        action_description=(
            "approve this contribution change" if approve else "reject this contribution change"
        ),
        permission_code=permission_code,
        entity_type="contribution_change_request",
        entity_id=str(row.id),
        request=request,
    )

    if row.status != models.ContributionChangeRequestStatus.PENDING:
        raise HTTPException(
            status_code=409,
            detail=f"This request has already been {row.status.value}",
        )

    previous_status = row.status
    previous_amount = member.monthly_contribution_amount
    row.reviewed_by_user_id = current_user.id
    row.reviewed_at = datetime.utcnow()
    row.review_reason = reason

    if approve:
        # The member may have left the cooperative since applying; an
        # amount that can never be deducted must not be approved into
        # place. Rejecting it is still allowed.
        contribution_rules.assert_may_have_contribution(member)
        effective_from = contribution_rules.next_month_start(date.today())
        member.monthly_contribution_amount = row.requested_amount
        member.contribution_effective_from = effective_from
        row.status = models.ContributionChangeRequestStatus.APPROVED
        row.effective_from = effective_from
        event_type, action = "contribution_change.approved", "approve"
    else:
        row.status = models.ContributionChangeRequestStatus.REJECTED
        event_type, action = "contribution_change.rejected", "reject"

    db.commit()

    row = _fetch(db, row.id)
    _audit(
        db,
        current_user,
        row,
        event_type=event_type,
        action=action,
        previous_status=previous_status,
        reason=reason,
        extra={
            "member_previous_amount": str(previous_amount) if previous_amount is not None else None,
            "member_new_amount": str(member.monthly_contribution_amount)
            if member.monthly_contribution_amount is not None
            else None,
        },
        request=request,
    )
    return row


@router.post(
    "/api/contribution-change-requests/{request_id}/approve",
    response_model=schemas.ContributionChangeRequestOut,
    dependencies=_officer_gate,
)
def approve_contribution_request(
    request_id: uuid.UUID,
    payload: schemas.ContributionChangeReviewRequest,
    request: Request,
    current_user: models.User = Depends(require_permission("savings.approve_change")),
    db: Session = Depends(get_db),
):
    return _review(
        db,
        current_user,
        request,
        request_id,
        approve=True,
        reason=(payload.reason or "").strip() or None,
        permission_code="savings.approve_change",
    )


@router.post(
    "/api/contribution-change-requests/{request_id}/reject",
    response_model=schemas.ContributionChangeRequestOut,
    dependencies=_officer_gate,
)
def reject_contribution_request(
    request_id: uuid.UUID,
    payload: schemas.ContributionChangeReviewRequest,
    request: Request,
    current_user: models.User = Depends(require_permission("savings.reject_change")),
    db: Session = Depends(get_db),
):
    reason = (payload.reason or "").strip()
    if not reason:
        raise HTTPException(
            status_code=422, detail="A reason is required when rejecting a contribution change"
        )
    return _review(
        db,
        current_user,
        request,
        request_id,
        approve=False,
        reason=reason,
        permission_code="savings.reject_change",
    )