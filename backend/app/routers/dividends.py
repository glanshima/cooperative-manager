"""Dividends API: policy summary, the run lifecycle, allocations, payouts
and the bank manifest.

The module flag gates every route. Creating, declaring and deleting runs
needs ``dividend.declare``; recording a payout batch needs
``dividend.pay``. Posting waits for open books, exactly like the rest of
the cashbook.
"""
import uuid
from datetime import date
from decimal import Decimal
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload

from .. import audit_service, cashbook, cooperative_settings, dividends, models, schemas
from ..database import get_db
from ..deps import require_module_enabled, require_permission

router = APIRouter(
    prefix="/api/dividends",
    tags=["dividends"],
    dependencies=[Depends(require_module_enabled("dividends"))],
)

ZERO = Decimal("0.00")


def _http(exc) -> HTTPException:
    # DividendError and CashbookError share the same shape: a status and a
    # message meant for the user.
    return HTTPException(status_code=exc.status_code, detail=exc.detail)


def _run_or_404(db: Session, run_id: uuid.UUID) -> models.DividendRun:
    run = (
        db.query(models.DividendRun)
        .options(
            joinedload(models.DividendRun.allocations).joinedload(
                models.DividendAllocation.member
            ),
            joinedload(models.DividendRun.payouts),
        )
        .filter(models.DividendRun.id == run_id)
        .first()
    )
    if run is None:
        raise HTTPException(status_code=404, detail="Dividend run not found")
    return run


def _allocation_out(allocation: models.DividendAllocation) -> schemas.DividendAllocationOut:
    member = allocation.member
    return schemas.DividendAllocationOut(
        id=allocation.id,
        member_id=allocation.member_id,
        psn=member.psn if member else "",
        name=member.name if member else "",
        bank_name=member.bank_name if member else None,
        account_number=member.account_number if member else None,
        basis_amount=allocation.basis_amount,
        share_ratio=allocation.share_ratio,
        gross_amount=allocation.gross_amount,
        withholding_amount=allocation.withholding_amount,
        net_amount=allocation.net_amount,
        rounding_adjustment=allocation.rounding_adjustment,
        payout_id=allocation.payout_id,
    )


def _detail(db: Session, run: models.DividendRun) -> schemas.DividendRunDetailOut:
    paid = sum(1 for allocation in run.allocations if allocation.payout_id is not None)
    return schemas.DividendRunDetailOut(
        run=schemas.DividendRunOut.model_validate(run),
        payouts=[schemas.DividendPayoutOut.model_validate(row) for row in run.payouts],
        paid_allocations=paid,
        pending_allocations=len(run.allocations) - paid,
    )


def _current_fiscal_year(settings: models.Settings, today: date) -> int:
    start_month = int(settings.fiscal_year_start_month or 1)
    return today.year if today.month >= start_month else today.year - 1


@router.get("/summary", response_model=schemas.DividendSummaryOut)
def summary(
    current_user: models.User = Depends(require_permission("dividend.view")),
    db: Session = Depends(get_db),
):
    settings = cooperative_settings.get_or_create(db)
    last = (
        db.query(models.DividendRun.fiscal_year)
        .filter(
            models.DividendRun.status.in_(
                [models.DividendRunStatus.DECLARED, models.DividendRunStatus.PAID]
            )
        )
        .order_by(models.DividendRun.fiscal_year.desc())
        .first()
    )
    last_year = last[0] if last else None
    suggested = last_year + 1 if last_year is not None else _current_fiscal_year(settings, date.today())
    return schemas.DividendSummaryOut(
        fiscal_year_start_month=settings.fiscal_year_start_month,
        basis=settings.dividend_basis,
        pool_mode=settings.dividend_pool_mode,
        reserve_pct=settings.dividend_reserve_pct,
        honorarium_pct=settings.dividend_honorarium_pct,
        payout_pct=settings.dividend_payout_pct,
        declared_rate_pct=settings.dividend_declared_rate_pct,
        fixed_pool_amount=settings.dividend_fixed_pool_amount,
        hybrid_savings_pct=settings.dividend_hybrid_savings_pct,
        min_membership_months=settings.dividend_min_membership_months,
        include_exited=settings.dividend_include_exited,
        rounding=settings.dividend_rounding,
        withholding_pct=settings.dividend_withholding_pct,
        payment_method=settings.dividend_payment_method,
        cashbook_module_enabled=bool(settings.cashbook_module_enabled),
        cashbook_open=cashbook.books_open(db),
        last_declared_year=last_year,
        suggested_fiscal_year=suggested,
    )


@router.get("/runs", response_model=List[schemas.DividendRunOut])
def list_runs(
    current_user: models.User = Depends(require_permission("dividend.view")),
    db: Session = Depends(get_db),
):
    runs = (
        db.query(models.DividendRun)
        .order_by(models.DividendRun.fiscal_year.desc())
        .all()
    )
    return [schemas.DividendRunOut.model_validate(run) for run in runs]


@router.post("/runs", response_model=schemas.DividendRunOut, status_code=201)
def create_draft(
    payload: schemas.DividendRunCreate,
    request: Request,
    current_user: models.User = Depends(require_permission("dividend.declare")),
    db: Session = Depends(get_db),
):
    try:
        run = dividends.create_or_update_draft(
            db,
            fiscal_year=payload.fiscal_year,
            actor_id=current_user.id,
            note=payload.note,
        )
    except (dividends.DividendError, cashbook.CashbookError) as exc:
        raise _http(exc)
    db.commit()
    run = _run_or_404(db, run.id)
    audit_service.log_event(
        db,
        actor=current_user,
        event_type="dividend.run_computed",
        action="create",
        entity_type="dividend_run",
        entity_id=str(run.id),
        new_values={
            "fiscal_year": run.fiscal_year,
            "surplus": str(run.surplus),
            "pool_amount": str(run.pool_amount),
            "eligible_member_count": run.eligible_member_count,
        },
        request=request,
    )
    return run


@router.get("/runs/{run_id}", response_model=schemas.DividendRunDetailOut)
def get_run(
    run_id: uuid.UUID,
    current_user: models.User = Depends(require_permission("dividend.view")),
    db: Session = Depends(get_db),
):
    return _detail(db, _run_or_404(db, run_id))


@router.patch("/runs/{run_id}", response_model=schemas.DividendRunOut)
def recompute_draft(
    run_id: uuid.UUID,
    payload: schemas.DividendRunUpdate,
    request: Request,
    current_user: models.User = Depends(require_permission("dividend.declare")),
    db: Session = Depends(get_db),
):
    run = _run_or_404(db, run_id)
    if run.status != models.DividendRunStatus.DRAFT:
        raise HTTPException(status_code=409, detail="Only a draft can be recomputed.")
    try:
        dividends.create_or_update_draft(
            db,
            fiscal_year=run.fiscal_year,
            actor_id=current_user.id,
            note=payload.note if payload.note is not None else run.note,
        )
    except (dividends.DividendError, cashbook.CashbookError) as exc:
        raise _http(exc)
    db.commit()
    run = _run_or_404(db, run.id)
    audit_service.log_event(
        db,
        actor=current_user,
        event_type="dividend.run_recomputed",
        action="update",
        entity_type="dividend_run",
        entity_id=str(run.id),
        new_values={
            "surplus": str(run.surplus),
            "pool_amount": str(run.pool_amount),
            "eligible_member_count": run.eligible_member_count,
        },
        request=request,
    )
    return run


@router.delete("/runs/{run_id}", status_code=204)
def delete_draft(
    run_id: uuid.UUID,
    request: Request,
    current_user: models.User = Depends(require_permission("dividend.declare")),
    db: Session = Depends(get_db),
):
    run = _run_or_404(db, run_id)
    fiscal_year = run.fiscal_year
    try:
        dividends.delete_draft(db, run)
    except (dividends.DividendError, cashbook.CashbookError) as exc:
        raise _http(exc)
    db.commit()
    audit_service.log_event(
        db,
        actor=current_user,
        event_type="dividend.run_deleted",
        action="delete",
        entity_type="dividend_run",
        entity_id=str(run_id),
        previous_values={"fiscal_year": fiscal_year},
        request=request,
    )
    return None


@router.get("/runs/{run_id}/allocations", response_model=schemas.DividendAllocationPageOut)
def list_allocations(
    run_id: uuid.UUID,
    q: Optional[str] = Query(default=None, max_length=120),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    current_user: models.User = Depends(require_permission("dividend.view")),
    db: Session = Depends(get_db),
):
    run = _run_or_404(db, run_id)
    query = (
        db.query(models.DividendAllocation)
        .join(models.Member, models.Member.id == models.DividendAllocation.member_id)
        .options(joinedload(models.DividendAllocation.member))
        .filter(models.DividendAllocation.run_id == run.id)
    )
    if q and q.strip():
        term = f"%{q.strip()}%"
        query = query.filter(or_(models.Member.psn.ilike(term), models.Member.name.ilike(term)))
    total = query.count()
    rows = (
        query.order_by(models.Member.psn.asc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    return schemas.DividendAllocationPageOut(
        items=[_allocation_out(row) for row in rows],
        total=total,
        skip=skip,
        limit=limit,
    )


@router.post("/runs/{run_id}/declare", response_model=schemas.DividendRunOut)
def declare_run(
    run_id: uuid.UUID,
    payload: schemas.DividendDeclareRequest,
    request: Request,
    current_user: models.User = Depends(require_permission("dividend.declare")),
    db: Session = Depends(get_db),
):
    run = _run_or_404(db, run_id)
    try:
        dividends.declare(
            db,
            run,
            actor_id=current_user.id,
            declared_on=payload.declared_on,
        )
    except (dividends.DividendError, cashbook.CashbookError) as exc:
        raise _http(exc)
    db.commit()
    db.refresh(run)
    audit_service.log_event(
        db,
        actor=current_user,
        event_type="dividend.declared",
        action="declare",
        entity_type="dividend_run",
        entity_id=str(run.id),
        new_values={
            "fiscal_year": run.fiscal_year,
            "surplus": str(run.surplus),
            "reserve_amount": str(run.reserve_amount),
            "honorarium_amount": str(run.honorarium_amount),
            "pool_amount": str(run.pool_amount),
            "declared_on": run.declared_on.isoformat() if run.declared_on else None,
        },
        request=request,
    )
    return run


@router.post(
    "/runs/{run_id}/payouts",
    response_model=schemas.DividendPayoutOut,
    status_code=201,
)
def record_payout(
    run_id: uuid.UUID,
    payload: schemas.DividendPayoutRequest,
    request: Request,
    current_user: models.User = Depends(require_permission("dividend.pay")),
    db: Session = Depends(get_db),
):
    run = _run_or_404(db, run_id)
    try:
        payout = dividends.record_payout(
            db,
            run,
            paid_on=payload.paid_on or date.today(),
            method=payload.method,
            reference=payload.reference,
            actor_id=current_user.id,
            allocation_ids=payload.allocation_ids,
            note=payload.note,
        )
    except (dividends.DividendError, cashbook.CashbookError) as exc:
        raise _http(exc)
    db.commit()
    db.refresh(payout)
    audit_service.log_event(
        db,
        actor=current_user,
        event_type="dividend.payout_recorded",
        action="pay",
        entity_type="dividend_run",
        entity_id=str(run.id),
        new_values={
            "payout_id": str(payout.id),
            "paid_on": payout.paid_on.isoformat(),
            "method": payout.method.value,
            "reference": payout.reference,
            "amount": str(payout.amount),
            "run_status": run.status.value,
        },
        request=request,
    )
    return payout


@router.get("/runs/{run_id}/manifest", response_model=schemas.DividendManifestOut)
def manifest(
    run_id: uuid.UUID,
    current_user: models.User = Depends(require_permission("dividend.view")),
    db: Session = Depends(get_db),
):
    run = _run_or_404(db, run_id)
    rows = dividends.manifest(run)
    total_gross = sum((row["gross_amount"] for row in rows), ZERO)
    total_withholding = sum((row["withholding_amount"] for row in rows), ZERO)
    total_net = sum((row["net_amount"] for row in rows), ZERO)
    return schemas.DividendManifestOut(
        fiscal_year=run.fiscal_year,
        reference=f"dividend-{run.fiscal_year}",
        rows=[schemas.DividendManifestRowOut(**row) for row in rows],
        total_gross=total_gross,
        total_withholding=total_withholding,
        total_net=total_net,
    )
