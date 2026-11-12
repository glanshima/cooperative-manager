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
from sqlalchemy import func
from sqlalchemy.orm import Session, contains_eager, joinedload

from .. import audit_service, deduction_expectations, models, schemas, validation
from ..database import get_db
from ..deps import require_module_enabled, require_permission
from ..loan_rules import assert_no_other_active_loan_of_type
from ..self_conflict import (
    get_conflicted_member_ids,
    log_conflicted_view,
    mark_conflicted_reads,
    require_no_member_conflict,
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
        return validation.month_start_from_label(value)
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


def _base_query(db: Session, *, include_void: bool = False):
    """Deductions for the month/schedule views. Voided records are hidden
    unless the caller explicitly asks for that status, so the ledger view
    stays clean without losing the append-only history.

    Every member's records are included, including those the caller is
    conflicted against: a payroll month must reconcile against the full
    schedule. Callers flag the conflicted rows instead (see
    self_conflict.py's read policy)."""
    query = (
        db.query(models.PayrollDeduction)
        .join(models.PayrollDeduction.member)
        .options(contains_eager(models.PayrollDeduction.member), *_DETAIL_OPTIONS[1:])
    )
    if not include_void:
        query = query.filter(models.PayrollDeduction.status != models.PayrollDeductionStatus.VOID)
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


def _assert_contribution_line_matches_membership(
    db: Session, member_id: uuid.UUID, lines: List[models.PayrollDeductionLine]
) -> None:
    """A contribution line IS a savings entry, and only financial members
    owe one -- so it must never be raised for a member who has left or
    lapsed, on pain of inventing savings they never paid in. Anything such
    a member still owes goes through an 'other' line, which is reported
    separately.

    Checked again at submission, not only while drafting: the member's
    status can change between those two moments (see withdraw_member)."""
    if not any(
        line.category == models.PayrollDeductionLineCategory.MONTHLY_CONTRIBUTION for line in lines
    ):
        return

    member_status = db.query(models.Member.status).filter(models.Member.id == member_id).scalar()
    if member_status == models.MemberStatus.FINANCIAL:
        return

    raise HTTPException(
        status_code=400,
        detail=(
            "The monthly contribution applies to financial members only. "
            "Record an amount owed by a non-financial member as an 'other' deduction."
        ),
    )


def _build_lines(
    db: Session,
    member: models.Member,
    expectation: deduction_expectations.MemberExpectation,
    inputs: List[schemas.PayrollDeductionLineInput],
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
    _assert_contribution_line_matches_membership(db, member.id, lines)
    _load_loans_for_lines(db, member.id, lines, lock=False)
    expectation.apply_to(lines)
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


def _guard_overrides(
    db: Session,
    current_user: models.User,
    member: models.Member,
    expectation: deduction_expectations.MemberExpectation,
    lines: List[models.PayrollDeductionLine],
    *,
    action_description: str,
    permission_code: str,
    request: Request,
    entity_type: str = "member",
    entity_id: Optional[str] = None,
) -> None:
    """A conflicted officer may record what the server already expects --
    that is clerical work on an agreed figure, not a decision about a
    relative's money. Typing a different amount is a decision, so it needs
    an officer with no conflict (409 member_conflict otherwise).

    Callers must run this BEFORE attaching anything to the session: the
    denial is audited, and writing an audit event commits."""
    if not any(expectation.is_override(line) for line in lines):
        return
    require_no_member_conflict(
        db,
        current_user,
        member,
        action_description=action_description,
        permission_code=permission_code,
        entity_type=entity_type,
        entity_id=entity_id if entity_id is not None else str(member.id),
        request=request,
    )


def _guard_transition(
    db: Session,
    current_user: models.User,
    deduction: models.PayrollDeduction,
    *,
    action: str,
    action_description: str,
    permission_code: str,
    request: Request,
) -> None:
    # Submitting a schedule of agreed figures is clerical, so a conflicted
    # officer may do it. Every step that recognises money (confirm),
    # excuses it (not_deducted) or reverses it (void) needs an unconflicted
    # officer, as does submitting anything the officer overrode.
    if action == "submit" and not deduction_expectations.has_override(deduction.lines):
        return
    _conflict_guard(
        db,
        current_user,
        deduction,
        action_description=action_description,
        permission_code=permission_code,
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


def _transition_submit(
    db: Session, deduction: models.PayrollDeduction, current_user: models.User
) -> None:
    if deduction.status != models.PayrollDeductionStatus.DRAFT:
        raise HTTPException(status_code=400, detail="Only draft deductions can be submitted")
    if not deduction.lines:
        raise HTTPException(status_code=400, detail="A deduction needs at least one line before submission")
    _assert_contribution_line_matches_membership(db, deduction.member_id, deduction.lines)
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


def _worklist_item(
    expectation: deduction_expectations.MemberExpectation,
    record: Optional[models.PayrollDeduction],
) -> schemas.DeductionWorklistItem:
    return schemas.DeductionWorklistItem(
        member_id=expectation.member_id,
        member_name=expectation.member_name,
        member_psn=expectation.member_psn,
        member_status=expectation.member_status,
        membership_exit_date=expectation.membership_exit_date,
        due_reasons=expectation.due_reasons,
        lines=[
            schemas.DeductionWorklistLine(
                category=line.category,
                amount=line.amount,
                loan_id=line.loan_id,
                loan_type_name=line.loan_type_name,
                arrears=line.arrears,
                months_behind=line.months_behind,
            )
            for line in expectation.lines
        ],
        warnings=expectation.warnings,
        expected_total=expectation.total,
        deduction_id=record.id if record else None,
        deduction_status=record.status if record else None,
    )


# ---------------------------------------------------------------------------
# Read endpoints
# ---------------------------------------------------------------------------

@router.get(
    "/api/payroll-deductions",
    response_model=schemas.PayrollDeductionListResponse,
)
def list_deductions(
    request: Request,
    month: Optional[str] = Query(default=None),
    status: Optional[models.PayrollDeductionStatus] = Query(default=None),
    member_id: Optional[uuid.UUID] = Query(default=None),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    current_user: models.User = Depends(require_permission("deduction.view")),
    db: Session = Depends(get_db),
):
    query = _base_query(db, include_void=status == models.PayrollDeductionStatus.VOID)
    if month is not None:
        query = query.filter(models.PayrollDeduction.deduction_month == _month_start(month))
    if status is not None:
        query = query.filter(models.PayrollDeduction.status == status)
    if member_id is not None:
        query = query.filter(models.PayrollDeduction.member_id == member_id)

    # Count before slicing so `total` describes the whole filtered set,
    # which is what the page controls and "submit all drafts" both need.
    total = query.count()
    records = (
        query.order_by(
            models.PayrollDeduction.deduction_month.desc(), models.Member.name
        )
        .offset(skip)
        .limit(limit)
        .all()
    )
    items = [schemas.PayrollDeductionOut.model_validate(r) for r in records]
    flagged = mark_conflicted_reads(items, get_conflicted_member_ids(db, current_user))
    log_conflicted_view(
        db,
        current_user,
        conflicted_count=flagged,
        action_description="browsed the deduction ledger",
        entity_type="payroll_deduction",
        request=request,
    )
    return schemas.PayrollDeductionListResponse(
        items=items, total=total, skip=skip, limit=limit
    )


@router.get(
    "/api/payroll-deductions/schedule",
    response_model=schemas.PayrollDeductionScheduleOut,
)
def get_schedule(
    request: Request,
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
        _base_query(db)
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
    response = schemas.PayrollDeductionScheduleOut(
        month=month_start, records=records, totals=totals
    )
    flagged = mark_conflicted_reads(response.records, get_conflicted_member_ids(db, current_user))
    log_conflicted_view(
        db,
        current_user,
        conflicted_count=flagged,
        action_description="opened the payroll deduction schedule",
        entity_type="payroll_deduction",
        request=request,
    )
    return response


@router.get(
    "/api/payroll-deductions/worklist",
    response_model=schemas.DeductionWorklistOut,
)
def get_worklist(
    request: Request,
    month: str = Query(..., description="Payroll month in YYYY-MM format"),
    entry_state: schemas.DeductionWorklistEntryState = Query(
        default=schemas.DeductionWorklistEntryState.PENDING,
        description="pending = still to enter, entered = already entered, all = both",
    ),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    current_user: models.User = Depends(require_permission("deduction.view")),
    db: Session = Depends(get_db),
):
    """Who still needs entering for a payroll month, with the amounts the
    server expects. A member appears only when something is actually due
    (a contribution, a missing contribution amount to resolve, or a loan
    instalment), so the pending queue shrinks as the officer works through
    it.

    The whole month is priced on every call, because the counts and
    `expected_total` beside the queue have to describe the month rather than
    the page -- an officer three pages in still needs to know how much of it
    is left. Paging pays for itself in the response size, and for_month
    batches the pricing lookups so the work stays a fixed handful of queries
    instead of one per member."""
    month_start = _month_start(month)

    entered = {
        record.member_id: record
        for record in db.query(models.PayrollDeduction)
        .filter(
            models.PayrollDeduction.deduction_month == month_start,
            models.PayrollDeduction.status != models.PayrollDeductionStatus.VOID,
        )
        .all()
    }

    rows: List[schemas.DeductionWorklistItem] = []
    due_count = 0
    pending_count = 0
    entered_count = 0
    expected_total = Decimal("0")

    for expectation in deduction_expectations.for_month(db, month_start):
        if not expectation.is_due:
            continue
        due_count += 1
        record = entered.get(expectation.member_id)
        if record is None:
            pending_count += 1
            expected_total += expectation.total
        else:
            entered_count += 1
        if entry_state == schemas.DeductionWorklistEntryState.PENDING and record is not None:
            continue
        if entry_state == schemas.DeductionWorklistEntryState.ENTERED and record is None:
            continue
        rows.append(_worklist_item(expectation, record))

    response = schemas.DeductionWorklistOut(
        month=month_start,
        items=rows[skip : skip + limit],
        total=len(rows),
        skip=skip,
        limit=limit,
        entry_state=entry_state,
        due_count=due_count,
        pending_count=pending_count,
        entered_count=entered_count,
        expected_total=expected_total,
    )
    flagged = mark_conflicted_reads(
        response.items, get_conflicted_member_ids(db, current_user)
    )
    log_conflicted_view(
        db,
        current_user,
        conflicted_count=flagged,
        action_description="opened the payroll deduction worklist",
        entity_type="payroll_deduction",
        request=request,
    )
    return response


@router.get(
    "/api/payroll-deductions/submittable-ids",
    response_model=schemas.PayrollDeductionSubmittableIds,
)
def get_submittable_ids(
    month: str = Query(..., description="YYYY-MM"),
    current_user: models.User = Depends(require_permission("deduction.submit")),
    db: Session = Depends(get_db),
):
    """Which drafts "submit all" would cover, decided where the data is.

    The ledger is paginated, so the browser can no longer enumerate a whole
    month from the rows it has loaded. Drafts with no lines are separated
    out here because _transition_submit rejects them: reporting them as
    "left as drafts" is honest, letting them fail in the batch would look
    like something broke.
    """
    month_start = _month_start(month)
    rows = (
        db.query(
            models.PayrollDeduction.id,
            func.count(models.PayrollDeductionLine.id),
        )
        .outerjoin(
            models.PayrollDeductionLine,
            models.PayrollDeductionLine.deduction_id == models.PayrollDeduction.id,
        )
        .filter(
            models.PayrollDeduction.deduction_month == month_start,
            models.PayrollDeduction.status == models.PayrollDeductionStatus.DRAFT,
        )
        .group_by(models.PayrollDeduction.id)
        .all()
    )

    submittable, empty = [], []
    for deduction_id, line_count in rows:
        (submittable if line_count else empty).append(deduction_id)

    return schemas.PayrollDeductionSubmittableIds(
        month=month_start,
        ids=sorted(submittable, key=str),
        empty_draft_ids=sorted(empty, key=str),
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

    conflicted = deduction.member_id in get_conflicted_member_ids(db, current_user)
    if conflicted:
        log_conflicted_view(
            db,
            current_user,
            conflicted_count=1,
            action_description="viewed a payroll deduction",
            entity_type="payroll_deduction",
            entity_id=str(deduction.id),
            request=request,
        )
    item = schemas.PayrollDeductionOut.model_validate(deduction)
    item.conflicted = conflicted
    return item


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

    month_start = validation.month_start_from_label(payload.deduction_month)
    _assert_no_live_record(db, member.id, month_start)

    expectation = deduction_expectations.for_member(db, member, month_start)
    lines = _build_lines(db, member, expectation, payload.lines)
    _guard_overrides(
        db,
        current_user,
        member,
        expectation,
        lines,
        action_description="enter an amount other than the expected deduction",
        permission_code="deduction.create",
        request=request,
    )

    deduction = models.PayrollDeduction(
        member_id=member.id,
        deduction_month=month_start,
        payroll_reference=payload.payroll_reference,
        note=payload.note,
        status=models.PayrollDeductionStatus.DRAFT,
        created_by_user_id=current_user.id,
    )
    deduction.lines = lines

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

    new_month = deduction.deduction_month
    if "deduction_month" in fields:
        new_month = validation.month_start_from_label(fields["deduction_month"])
        _assert_no_live_record(db, deduction.member_id, new_month, exclude_id=deduction.id)

    expectation = deduction_expectations.for_member(db, deduction.member, new_month)
    lines = (
        _build_lines(db, deduction.member, expectation, payload.lines)
        if "lines" in fields
        else list(deduction.lines)
    )
    _guard_overrides(
        db,
        current_user,
        deduction.member,
        expectation,
        lines,
        action_description="enter an amount other than the expected deduction",
        permission_code="deduction.create",
        request=request,
        entity_type="payroll_deduction",
        entity_id=str(deduction.id),
    )

    deduction.deduction_month = new_month
    if "payroll_reference" in fields:
        deduction.payroll_reference = fields["payroll_reference"]
    if "note" in fields:
        deduction.note = fields["note"]

    if "lines" in fields:
        deduction.lines = lines
    else:
        # Moving a draft to another month reprices its lines even when the
        # amounts themselves were not edited.
        expectation.apply_to(deduction.lines)

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

            _guard_transition(
                db,
                current_user,
                deduction,
                action=action,
                action_description=action_description,
                permission_code=permission_code,
                request=request,
            )
            previous_status = deduction.status

            if action == "submit":
                _transition_submit(db, deduction, current_user)
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
            # A conflict denial audits itself, and writing an audit event
            # commits -- which closes this savepoint. Nothing of this
            # record's was pending at that point (the guard runs before any
            # mutation), so there is only something to roll back when the
            # refusal came from a later check.
            if savepoint.is_active:
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

    _guard_transition(
        db,
        current_user,
        deduction,
        action=action,
        action_description=action_description,
        permission_code=permission_code,
        request=request,
    )
    previous_status = deduction.status

    if action == "submit":
        _transition_submit(db, deduction, current_user)
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
