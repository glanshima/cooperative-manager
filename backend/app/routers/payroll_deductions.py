"""
Monthly payroll deductions.

Staff cooperative members have their contributions, loan repayments and
other agreed deductions taken directly from month-end payroll by PSN.
This router is the ledger of that process:

  draft       entries are being prepared (editable)
  submitted   the printed schedule has gone to the payroll department
  confirmed   payroll actually deducted and remitted the money
  not_deducted payroll skipped this member; they pay by bank/cash and use
              the existing repayment evidence flow instead
  void        append-only correction; a confirmed record is reversed

The key financial rule: Loan.amount_repaid changes only on `confirmed`,
never on draft/submitted, because until payroll remits, the cooperative
has not received the money. Voiding a confirmed record reverses exactly
what it credited and reopens any loan it had completed.
"""
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session, contains_eager, joinedload

from .. import audit_service, models, schemas, validation
from ..database import get_db
from ..deps import require_module_enabled, require_permission
from ..loan_rules import assert_no_other_active_loan_of_type
from ..self_conflict import (
    get_conflicted_member_ids,
    require_no_member_conflict,
    require_no_nok_read_conflict,
)

router = APIRouter(
    tags=["payroll-deductions"],
    dependencies=[Depends(require_module_enabled("deductions"))],
)

_DETAIL_OPTIONS = (
    joinedload(models.PayrollDeduction.member),
    joinedload(models.PayrollDeduction.lines)
    .joinedload(models.PayrollDeductionLine.loan)
    .joinedload(models.Loan.loan_type),
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _month_start(value: str) -> date:
    try:
        return validation.deduction_month_start(value)
    except ValueError:
        raise HTTPException(status_code=422, detail="month must be in YYYY-MM format")


def _fetch(db: Session, deduction_id: uuid.UUID) -> Optional[models.PayrollDeduction]:
    return (
        db.query(models.PayrollDeduction)
        .options(*_DETAIL_OPTIONS)
        .filter(models.PayrollDeduction.id == deduction_id)
        .first()
    )


def _fetch_locked(db: Session, deduction_id: uuid.UUID) -> Optional[models.PayrollDeduction]:
    # of=...: the joined loads above are outer joins, which Postgres
    # rejects for a bare FOR UPDATE (same constraint documented in
    # routers/loan_repayments.py).
    return (
        db.query(models.PayrollDeduction)
        .options(*_DETAIL_OPTIONS)
        .filter(models.PayrollDeduction.id == deduction_id)
        .with_for_update(of=models.PayrollDeduction)
        .first()
    )


def _base_query(db: Session, current_user: models.User, *, include_void: bool = False):
    """Deductions for the month/schedule views, excluding members the actor
    is conflicted with (read boundary, see self_conflict.py). Voided
    records are hidden unless the caller explicitly asks for that status,
    so the ledger view stays clean without losing the append-only history."""
    query = (
        db.query(models.PayrollDeduction)
        .join(models.PayrollDeduction.member)
        .options(contains_eager(models.PayrollDeduction.member), *_DETAIL_OPTIONS[1:])
    )
    if not include_void:
        query = query.filter(models.PayrollDeduction.status != models.PayrollDeductionStatus.VOID)
    conflicted = get_conflicted_member_ids(db, current_user)
    if conflicted:
        query = query.filter(models.PayrollDeduction.member_id.notin_(conflicted))
    return query


def _load_loans_for_lines(
    db: Session,
    member_id: uuid.UUID,
    lines: List[models.PayrollDeductionLine],
    *,
    lock: bool,
    for_reversal: bool = False,
) -> dict:
    """Validates every loan line against the member's actual loan state and
    returns {loan_id: Loan}. With lock=True the rows are FOR UPDATE, so the
    balance checked here is the balance the caller then mutates.

    for_reversal=True is for voiding a confirmed record: the loan may now
    be completed (that is exactly what this deduction may have caused), so
    the active/remaining-balance checks that apply when crediting are not
    appropriate -- only ownership and existence still are."""
    loan_ids = [line.loan_id for line in lines if line.loan_id is not None]
    if not loan_ids:
        return {}

    query = db.query(models.Loan).filter(models.Loan.id.in_(loan_ids))
    if lock:
        query = query.with_for_update()
    loans = {loan.id: loan for loan in query.all()}

    for line in lines:
        if line.loan_id is None:
            continue
        loan = loans.get(line.loan_id)
        if loan is None:
            raise HTTPException(status_code=400, detail=f"Loan {line.loan_id} not found")
        if loan.member_id != member_id:
            raise HTTPException(
                status_code=400,
                detail=f"Loan {line.loan_id} does not belong to this member",
            )
        if for_reversal:
            continue
        if loan.status != models.LoanStatus.ACTIVE:
            raise HTTPException(
                status_code=400,
                detail=f"Loan {line.loan_id} is not active and cannot take a repayment line",
            )
        remaining = loan.total_repayable - loan.amount_repaid
        if line.amount > remaining:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Loan {line.loan_id} line of {line.amount} exceeds the "
                    f"remaining balance of {remaining}"
                ),
            )
    return loans


def _build_lines(
    db: Session, member_id: uuid.UUID, inputs: List[schemas.PayrollDeductionLineInput]
) -> List[models.PayrollDeductionLine]:
    lines = [
        models.PayrollDeductionLine(
            category=item.category,
            loan_id=item.loan_id,
            label=item.label,
            amount=item.amount,
        )
        for item in inputs
    ]
    _load_loans_for_lines(db, member_id, lines, lock=False)
    return lines


def _assert_no_live_record(
    db: Session, member_id: uuid.UUID, month: date, *, exclude_id: Optional[uuid.UUID] = None
) -> None:
    query = db.query(models.PayrollDeduction).filter(
        models.PayrollDeduction.member_id == member_id,
        models.PayrollDeduction.deduction_month == month,
        models.PayrollDeduction.status != models.PayrollDeductionStatus.VOID,
    )
    if exclude_id is not None:
        query = query.filter(models.PayrollDeduction.id != exclude_id)
    if query.first() is not None:
        raise HTTPException(
            status_code=400,
            detail="A deduction record already exists for this member and month",
        )


def _conflict_guard(
    db: Session,
    current_user: models.User,
    deduction: models.PayrollDeduction,
    *,
    action_description: str,
    permission_code: str,
    request: Request,
) -> None:
    require_no_member_conflict(
        db,
        current_user,
        deduction.member_id,
        action_description=action_description,
        permission_code=permission_code,
        entity_type="payroll_deduction",
        entity_id=str(deduction.id),
        request=request,
    )


def _audit(
    db: Session,
    actor: models.User,
    deduction: models.PayrollDeduction,
    *,
    event_type: str,
    action: str,
    previous_status: models.PayrollDeductionStatus,
    reason: Optional[str] = None,
    request: Optional[Request] = None,
) -> None:
    audit_service.log_event(
        db,
        actor=actor,
        event_type=event_type,
        action=action,
        entity_type="payroll_deduction",
        entity_id=str(deduction.id),
        previous_values={"status": previous_status.value},
        new_values={
            "status": deduction.status.value,
            "member_id": str(deduction.member_id),
            "deduction_month": deduction.deduction_month.isoformat(),
            "grand_total": str(deduction.grand_total),
        },
        reason=reason,
        request=request,
    )


def _transition_submit(deduction: models.PayrollDeduction, current_user: models.User) -> None:
    if deduction.status != models.PayrollDeductionStatus.DRAFT:
        raise HTTPException(status_code=400, detail="Only draft deductions can be submitted")
    if not deduction.lines:
        raise HTTPException(status_code=400, detail="A deduction needs at least one line before submission")
    deduction.status = models.PayrollDeductionStatus.SUBMITTED
    deduction.submitted_by_user_id = current_user.id
    deduction.submitted_at = datetime.utcnow()


def _transition_return_to_draft(
    deduction: models.PayrollDeduction, reason: str
) -> None:
    if deduction.status != models.PayrollDeductionStatus.SUBMITTED:
        raise HTTPException(status_code=400, detail="Only submitted deductions can be returned to draft")
    deduction.status = models.PayrollDeductionStatus.DRAFT
    deduction.returned_at = datetime.utcnow()
    deduction.return_reason = reason


def _transition_confirm(
    db: Session, deduction: models.PayrollDeduction, current_user: models.User
) -> None:
    if deduction.status != models.PayrollDeductionStatus.SUBMITTED:
        raise HTTPException(status_code=400, detail="Only submitted deductions can be confirmed")

    # Validate everything before mutating anything: a record either
    # applies in full or not at all.
    loans = _load_loans_for_lines(db, deduction.member_id, deduction.lines, lock=True)

    for line in deduction.lines:
        if line.loan_id is None:
            continue
        loan = loans[line.loan_id]
        loan.amount_repaid = loan.amount_repaid + line.amount
        if loan.amount_repaid >= loan.total_repayable:
            loan.status = models.LoanStatus.COMPLETED

    deduction.status = models.PayrollDeductionStatus.CONFIRMED
    deduction.confirmed_by_user_id = current_user.id
    deduction.confirmed_at = datetime.utcnow()


def _transition_not_deducted(
    deduction: models.PayrollDeduction, current_user: models.User, reason: str
) -> None:
    if deduction.status not in (
        models.PayrollDeductionStatus.DRAFT,
        models.PayrollDeductionStatus.SUBMITTED,
    ):
        raise HTTPException(
            status_code=400,
            detail="Only draft or submitted deductions can be marked not deducted",
        )
    deduction.status = models.PayrollDeductionStatus.NOT_DEDUCTED
    deduction.not_deducted_by_user_id = current_user.id
    deduction.not_deducted_at = datetime.utcnow()
    deduction.not_deducted_reason = reason


def _transition_void(
    db: Session, deduction: models.PayrollDeduction, current_user: models.User, reason: str
) -> None:
    if deduction.status == models.PayrollDeductionStatus.VOID:
        raise HTTPException(status_code=400, detail="This deduction is already void")

    if deduction.status == models.PayrollDeductionStatus.CONFIRMED:
        loans = _load_loans_for_lines(
            db, deduction.member_id, deduction.lines, lock=True, for_reversal=True
        )
        for line in deduction.lines:
            if line.loan_id is None:
                continue
            loan = loans[line.loan_id]
            if loan.amount_repaid < line.amount:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"Cannot void: loan {loan.id} has less recorded repaid "
                        f"({loan.amount_repaid}) than this deduction credited ({line.amount})"
                    ),
                )
            if (
                loan.status == models.LoanStatus.COMPLETED
                and loan.amount_repaid - line.amount < loan.total_repayable
            ):
                assert_no_other_active_loan_of_type(
                    db, loan.member_id, loan.loan_type_id, exclude_loan_ids=[loan.id]
                )
        for line in deduction.lines:
            if line.loan_id is None:
                continue
            loan = loans[line.loan_id]
            loan.amount_repaid = loan.amount_repaid - line.amount
            if (
                loan.status == models.LoanStatus.COMPLETED
                and loan.amount_repaid < loan.total_repayable
            ):
                loan.status = models.LoanStatus.ACTIVE

    deduction.status = models.PayrollDeductionStatus.VOID
    deduction.voided_by_user_id = current_user.id
    deduction.voided_at = datetime.utcnow()
    deduction.void_reason = reason


def _http_detail_text(exc: HTTPException) -> str:
    if isinstance(exc.detail, str):
        return exc.detail
    if isinstance(exc.detail, dict):
        return exc.detail.get("message") or str(exc.detail)
    return str(exc.detail)


# ---------------------------------------------------------------------------
# Read endpoints
# ---------------------------------------------------------------------------

@router.get("/api/payroll-deductions", response_model=List[schemas.PayrollDeductionOut])
def list_deductions(
    month: Optional[str] = Query(default=None),
    status: Optional[models.PayrollDeductionStatus] = Query(default=None),
    member_id: Optional[uuid.UUID] = Query(default=None),
    current_user: models.User = Depends(require_permission("deduction.view")),
    db: Session = Depends(get_db),
):
    query = _base_query(
        db, current_user, include_void=status == models.PayrollDeductionStatus.VOID
    )
    if month is not None:
        query = query.filter(models.PayrollDeduction.deduction_month == _month_start(month))
    if status is not None:
        query = query.filter(models.PayrollDeduction.status == status)
    if member_id is not None:
        query = query.filter(models.PayrollDeduction.member_id == member_id)

    return query.order_by(
        models.PayrollDeduction.deduction_month.desc(), models.Member.name
    ).all()


@router.get(
    "/api/payroll-deductions/schedule",
    response_model=schemas.PayrollDeductionScheduleOut,
)
def get_schedule(
    month: str = Query(..., description="Payroll month in YYYY-MM format"),
    current_user: models.User = Depends(require_permission("deduction.view")),
    db: Session = Depends(get_db),
):
    """The printable month schedule. Totals cover records that are
    expected to be deducted (draft/submitted/confirmed); not-deducted
    records are still listed for visibility but are excluded from the
    totals so payroll doesn't deduct them twice."""
    month_start = _month_start(month)
    records = (
        _base_query(db, current_user)
        .filter(models.PayrollDeduction.deduction_month == month_start)
        .order_by(models.Member.name)
        .all()
    )

    countable = {
        models.PayrollDeductionStatus.DRAFT,
        models.PayrollDeductionStatus.SUBMITTED,
        models.PayrollDeductionStatus.CONFIRMED,
    }
    totals = schemas.PayrollDeductionTotals(
        contribution_total=sum(
            (r.contribution_total for r in records if r.status in countable), Decimal("0")
        ),
        loan_total=sum((r.loan_total for r in records if r.status in countable), Decimal("0")),
        other_total=sum((r.other_total for r in records if r.status in countable), Decimal("0")),
        grand_total=sum((r.grand_total for r in records if r.status in countable), Decimal("0")),
    )
    return schemas.PayrollDeductionScheduleOut(
        month=month_start, records=records, totals=totals
    )


@router.get(
    "/api/payroll-deductions/{deduction_id}",
    response_model=schemas.PayrollDeductionOut,
)
def get_deduction(
    deduction_id: uuid.UUID,
    request: Request,
    current_user: models.User = Depends(require_permission("deduction.view")),
    db: Session = Depends(get_db),
):
    deduction = _fetch(db, deduction_id)
    if deduction is None:
        raise HTTPException(status_code=404, detail="Deduction not found")

    require_no_nok_read_conflict(
        db,
        current_user,
        deduction.member_id,
        action_description="view this payroll deduction",
        entity_type="payroll_deduction",
        entity_id=str(deduction.id),
        request=request,
    )
    return deduction


# ---------------------------------------------------------------------------
# Draft create/edit
# ---------------------------------------------------------------------------

@router.post(
    "/api/payroll-deductions",
    response_model=schemas.PayrollDeductionOut,
    status_code=201,
)
def create_deduction(
    payload: schemas.PayrollDeductionCreate,
    request: Request,
    current_user: models.User = Depends(require_permission("deduction.create")),
    db: Session = Depends(get_db),
):
    member = db.query(models.Member).filter(models.Member.id == payload.member_id).first()
    if member is None:
        raise HTTPException(status_code=404, detail="Member not found")

    month_start = validation.deduction_month_start(payload.deduction_month)
    _assert_no_live_record(db, member.id, month_start)

    deduction = models.PayrollDeduction(
        member_id=member.id,
        deduction_month=month_start,
        payroll_reference=payload.payroll_reference,
        note=payload.note,
        status=models.PayrollDeductionStatus.DRAFT,
        created_by_user_id=current_user.id,
    )
    deduction.lines = _build_lines(db, member.id, payload.lines)

    db.add(deduction)
    db.commit()

    deduction = _fetch(db, deduction.id)
    _audit(
        db,
        current_user,
        deduction,
        event_type="payroll_deduction.created",
        action="create",
        previous_status=models.PayrollDeductionStatus.DRAFT,
        request=request,
    )
    return deduction


@router.put(
    "/api/payroll-deductions/{deduction_id}",
    response_model=schemas.PayrollDeductionOut,
)
def update_deduction(
    deduction_id: uuid.UUID,
    payload: schemas.PayrollDeductionUpdate,
    request: Request,
    current_user: models.User = Depends(require_permission("deduction.create")),
    db: Session = Depends(get_db),
):
    deduction = _fetch_locked(db, deduction_id)
    if deduction is None:
        raise HTTPException(status_code=404, detail="Deduction not found")
    if deduction.status != models.PayrollDeductionStatus.DRAFT:
        raise HTTPException(status_code=400, detail="Only draft deductions can be edited")

    fields = payload.model_dump(exclude_unset=True)

    if "deduction_month" in fields:
        month_start = validation.deduction_month_start(fields["deduction_month"])
        _assert_no_live_record(
            db, deduction.member_id, month_start, exclude_id=deduction.id
        )
        deduction.deduction_month = month_start

    if "payroll_reference" in fields:
        deduction.payroll_reference = fields["payroll_reference"]
    if "note" in fields:
        deduction.note = fields["note"]

    if "lines" in fields:
        deduction.lines = _build_lines(db, deduction.member_id, payload.lines)

    db.commit()

    deduction = _fetch(db, deduction.id)
    _audit(
        db,
        current_user,
        deduction,
        event_type="payroll_deduction.updated",
        action="update",
        previous_status=models.PayrollDeductionStatus.DRAFT,
        request=request,
    )
    return deduction


# ---------------------------------------------------------------------------
# Bulk transitions
#
# Each id is processed in its own savepoint, so one bad record (e.g. an
# already-confirmed sibling or a stale loan balance) is reported in the
# result list without aborting the rest of the batch.
# ---------------------------------------------------------------------------

def _run_bulk(
    db: Session,
    current_user: models.User,
    request: Request,
    payload: schemas.PayrollDeductionBulkRequest,
    *,
    action: str,
    permission_code: str,
    action_description: str,
    reason: Optional[str],
):
    results = []
    for deduction_id in payload.ids:
        savepoint = db.begin_nested()
        try:
            deduction = _fetch_locked(db, deduction_id)
            if deduction is None:
                raise HTTPException(status_code=404, detail="Deduction not found")

            _conflict_guard(
                db,
                current_user,
                deduction,
                action_description=action_description,
                permission_code=permission_code,
                request=request,
            )
            previous_status = deduction.status

            if action == "submit":
                _transition_submit(deduction, current_user)
                event_type, audit_action = "payroll_deduction.submitted", "submit"
            elif action == "confirm":
                _transition_confirm(db, deduction, current_user)
                event_type, audit_action = "payroll_deduction.confirmed", "approve"
            elif action == "not_deducted":
                _transition_not_deducted(deduction, current_user, reason)
                event_type, audit_action = "payroll_deduction.not_deducted", "reject"
            elif action == "void":
                _transition_void(db, deduction, current_user, reason)
                event_type, audit_action = "payroll_deduction.voided", "reverse"
            else:
                raise ValueError(f"Unknown bulk action: {action}")

            new_status = deduction.status
            db.flush()
            savepoint.commit()
            results.append(
                schemas.PayrollDeductionBulkResult(
                    id=deduction_id, ok=True, status=new_status
                )
            )
        except HTTPException as exc:
            savepoint.rollback()
            results.append(
                schemas.PayrollDeductionBulkResult(
                    id=deduction_id, ok=False, detail=_http_detail_text(exc)
                )
            )
            continue

        _audit(
            db,
            current_user,
            deduction,
            event_type=event_type,
            action=audit_action,
            previous_status=previous_status,
            reason=reason,
            request=request,
        )

    db.commit()
    return schemas.PayrollDeductionBulkResponse(results=results)


@router.post(
    "/api/payroll-deductions/bulk/submit",
    response_model=schemas.PayrollDeductionBulkResponse,
)
def bulk_submit(
    payload: schemas.PayrollDeductionBulkRequest,
    request: Request,
    current_user: models.User = Depends(require_permission("deduction.submit")),
    db: Session = Depends(get_db),
):
    return _run_bulk(
        db,
        current_user,
        request,
        payload,
        action="submit",
        permission_code="deduction.submit",
        action_description="submit this payroll deduction",
        reason=None,
    )


@router.post(
    "/api/payroll-deductions/bulk/confirm",
    response_model=schemas.PayrollDeductionBulkResponse,
)
def bulk_confirm(
    payload: schemas.PayrollDeductionBulkRequest,
    request: Request,
    current_user: models.User = Depends(require_permission("deduction.confirm")),
    db: Session = Depends(get_db),
):
    return _run_bulk(
        db,
        current_user,
        request,
        payload,
        action="confirm",
        permission_code="deduction.confirm",
        action_description="confirm this payroll deduction",
        reason=None,
    )


@router.post(
    "/api/payroll-deductions/bulk/not-deducted",
    response_model=schemas.PayrollDeductionBulkResponse,
)
def bulk_not_deducted(
    payload: schemas.PayrollDeductionBulkRequest,
    request: Request,
    current_user: models.User = Depends(require_permission("deduction.confirm")),
    db: Session = Depends(get_db),
):
    if not (payload.reason or "").strip():
        raise HTTPException(status_code=422, detail="A reason is required when marking deductions not deducted")
    return _run_bulk(
        db,
        current_user,
        request,
        payload,
        action="not_deducted",
        permission_code="deduction.confirm",
        action_description="mark this payroll deduction as not deducted",
        reason=payload.reason.strip(),
    )


@router.post(
    "/api/payroll-deductions/bulk/void",
    response_model=schemas.PayrollDeductionBulkResponse,
)
def bulk_void(
    payload: schemas.PayrollDeductionBulkRequest,
    request: Request,
    current_user: models.User = Depends(require_permission("deduction.void")),
    db: Session = Depends(get_db),
):
    if not (payload.reason or "").strip():
        raise HTTPException(status_code=422, detail="A reason is required when voiding deductions")
    return _run_bulk(
        db,
        current_user,
        request,
        payload,
        action="void",
        permission_code="deduction.void",
        action_description="void this payroll deduction",
        reason=payload.reason.strip(),
    )


# ---------------------------------------------------------------------------
# Single-record transitions
# ---------------------------------------------------------------------------

def _transition_response(
    db: Session,
    current_user: models.User,
    request: Request,
    deduction_id: uuid.UUID,
    *,
    action: str,
    permission_code: str,
    action_description: str,
    reason: Optional[str] = None,
):
    deduction = _fetch_locked(db, deduction_id)
    if deduction is None:
        raise HTTPException(status_code=404, detail="Deduction not found")

    _conflict_guard(
        db,
        current_user,
        deduction,
        action_description=action_description,
        permission_code=permission_code,
        request=request,
    )
    previous_status = deduction.status

    if action == "submit":
        _transition_submit(deduction, current_user)
        event_type, audit_action = "payroll_deduction.submitted", "submit"
    elif action == "return_to_draft":
        _transition_return_to_draft(deduction, reason)
        event_type, audit_action = "payroll_deduction.returned_to_draft", "return"
    elif action == "confirm":
        _transition_confirm(db, deduction, current_user)
        event_type, audit_action = "payroll_deduction.confirmed", "approve"
    elif action == "not_deducted":
        _transition_not_deducted(deduction, current_user, reason)
        event_type, audit_action = "payroll_deduction.not_deducted", "reject"
    elif action == "void":
        _transition_void(db, deduction, current_user, reason)
        event_type, audit_action = "payroll_deduction.voided", "reverse"
    else:
        raise ValueError(f"Unknown action: {action}")

    db.commit()

    deduction = _fetch(db, deduction.id)
    _audit(
        db,
        current_user,
        deduction,
        event_type=event_type,
        action=audit_action,
        previous_status=previous_status,
        reason=reason,
        request=request,
    )
    return deduction


@router.post(
    "/api/payroll-deductions/{deduction_id}/submit",
    response_model=schemas.PayrollDeductionOut,
)
def submit_deduction(
    deduction_id: uuid.UUID,
    request: Request,
    current_user: models.User = Depends(require_permission("deduction.submit")),
    db: Session = Depends(get_db),
):
    return _transition_response(
        db,
        current_user,
        request,
        deduction_id,
        action="submit",
        permission_code="deduction.submit",
        action_description="submit this payroll deduction",
    )


@router.post(
    "/api/payroll-deductions/{deduction_id}/return-to-draft",
    response_model=schemas.PayrollDeductionOut,
)
def return_deduction_to_draft(
    deduction_id: uuid.UUID,
    payload: schemas.PayrollDeductionReasonRequest,
    request: Request,
    current_user: models.User = Depends(require_permission("deduction.submit")),
    db: Session = Depends(get_db),
):
    return _transition_response(
        db,
        current_user,
        request,
        deduction_id,
        action="return_to_draft",
        permission_code="deduction.submit",
        action_description="return this payroll deduction to draft",
        reason=payload.reason,
    )


@router.post(
    "/api/payroll-deductions/{deduction_id}/confirm",
    response_model=schemas.PayrollDeductionOut,
)
def confirm_deduction(
    deduction_id: uuid.UUID,
    request: Request,
    current_user: models.User = Depends(require_permission("deduction.confirm")),
    db: Session = Depends(get_db),
):
    return _transition_response(
        db,
        current_user,
        request,
        deduction_id,
        action="confirm",
        permission_code="deduction.confirm",
        action_description="confirm this payroll deduction",
    )


@router.post(
    "/api/payroll-deductions/{deduction_id}/not-deducted",
    response_model=schemas.PayrollDeductionOut,
)
def mark_deduction_not_deducted(
    deduction_id: uuid.UUID,
    payload: schemas.PayrollDeductionReasonRequest,
    request: Request,
    current_user: models.User = Depends(require_permission("deduction.confirm")),
    db: Session = Depends(get_db),
):
    return _transition_response(
        db,
        current_user,
        request,
        deduction_id,
        action="not_deducted",
        permission_code="deduction.confirm",
        action_description="mark this payroll deduction as not deducted",
        reason=payload.reason,
    )


@router.post(
    "/api/payroll-deductions/{deduction_id}/void",
    response_model=schemas.PayrollDeductionOut,
)
def void_deduction(
    deduction_id: uuid.UUID,
    payload: schemas.PayrollDeductionReasonRequest,
    request: Request,
    current_user: models.User = Depends(require_permission("deduction.void")),
    db: Session = Depends(get_db),
):
    return _transition_response(
        db,
        current_user,
        request,
        deduction_id,
        action="void",
        permission_code="deduction.void",
        action_description="void this payroll deduction",
        reason=payload.reason,
    )
