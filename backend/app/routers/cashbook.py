"""Cashbook API: chart of accounts, journal, opening balances, locks and
the financial reports.

The module flag gates every route. Recording entries additionally waits
for the opening journal -- see app/cashbook.py -- so a book can never
start mid-way through its own history.
"""
import uuid
from datetime import date
from decimal import Decimal
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload

from .. import audit_service, cashbook, models, schemas
from ..database import get_db
from ..deps import (
    require_any_permission,
    require_module_enabled,
    require_permission,
)

router = APIRouter(
    prefix="/api/cashbook",
    tags=["cashbook"],
    dependencies=[Depends(require_module_enabled("cashbook"))],
)

ZERO = Decimal("0.00")

_REPORT_ACCESS = require_any_permission("report.financial", "report.accounting")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _http(exc: cashbook.CashbookError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=exc.detail)


def _account_out(account: models.CashbookAccount) -> schemas.CashbookAccountOut:
    return schemas.CashbookAccountOut.model_validate(account)


def _entry_out(entry: models.CashbookEntry) -> schemas.CashbookEntryOut:
    return schemas.CashbookEntryOut(
        id=entry.id,
        entry_date=entry.entry_date,
        narration=entry.narration,
        reference=entry.reference,
        source=entry.source,
        source_id=entry.source_id,
        reverses_entry_id=entry.reverses_entry_id,
        reversal_reason=entry.reversal_reason,
        posted_by_user_id=entry.posted_by_user_id,
        posted_at=entry.posted_at,
        lines=[
            schemas.CashbookLineOut(
                id=line.id,
                account_id=line.account_id,
                account_code=line.account.code,
                account_name=line.account.name,
                debit=line.debit,
                credit=line.credit,
            )
            for line in entry.lines
        ],
    )


def _resolve_lines(
    db: Session, lines: List[schemas.CashbookLineIn]
) -> List[tuple]:
    ids = {line.account_id for line in lines}
    accounts = {
        account.id: account
        for account in db.query(models.CashbookAccount)
        .filter(models.CashbookAccount.id.in_(ids))
        .all()
    }
    resolved = []
    for line in lines:
        account = accounts.get(line.account_id)
        if account is None:
            raise HTTPException(
                status_code=400, detail=f"Account {line.account_id} does not exist"
            )
        if not account.is_active:
            raise HTTPException(
                status_code=400,
                detail=f"Account {account.code} {account.name} is inactive",
            )
        resolved.append((account, line.debit, line.credit))
    return resolved


def _system_balance(
    db: Session, key: str, *, as_of: Optional[date] = None
) -> Decimal:
    account = (
        db.query(models.CashbookAccount)
        .filter(models.CashbookAccount.system_key == key)
        .first()
    )
    if account is None:
        return ZERO
    totals = cashbook.account_ledger(db, account, end=as_of)
    return totals.closing_balance


def _cashbook_entry_or_404(db: Session, entry_id: uuid.UUID) -> models.CashbookEntry:
    entry = (
        db.query(models.CashbookEntry)
        .options(
            joinedload(models.CashbookEntry.lines).joinedload(
                models.CashbookLine.account
            )
        )
        .filter(models.CashbookEntry.id == entry_id)
        .first()
    )
    if entry is None:
        raise HTTPException(status_code=404, detail="Cashbook entry not found")
    return entry


# ---------------------------------------------------------------------------
# Overview and chart of accounts
# ---------------------------------------------------------------------------

@router.get("/overview", response_model=schemas.CashbookOverviewOut)
def overview(
    current_user: models.User = Depends(require_permission("accounting.view")),
    db: Session = Depends(get_db),
):
    opening = cashbook.opening_entry(db)
    accounts = db.query(models.CashbookAccount).count()
    entries = db.query(models.CashbookEntry).count()
    locks = cashbook.period_locks(db)
    return schemas.CashbookOverviewOut(
        enabled=True,
        opened=opening is not None,
        opening_entry_id=opening.id if opening else None,
        opening_date=opening.entry_date if opening else None,
        account_count=accounts,
        entry_count=entries,
        cash_balance=_system_balance(db, cashbook.CASH),
        bank_balance=_system_balance(db, cashbook.BANK),
        current_month_locked=cashbook.is_locked(db, date.today()),
        locked_periods=[lock.period_start for lock in locks],
    )


@router.get("/accounts", response_model=List[schemas.CashbookAccountBalanceOut])
def list_accounts(
    as_of: Optional[date] = Query(default=None),
    current_user: models.User = Depends(require_permission("accounting.view")),
    db: Session = Depends(get_db),
):
    accounts = (
        db.query(models.CashbookAccount)
        .order_by(models.CashbookAccount.code.asc())
        .all()
    )
    totals = {
        row.account.id: row for row in cashbook.account_balances(db, as_of=as_of)
    }
    result: List[schemas.CashbookAccountBalanceOut] = []
    for account in accounts:
        item = totals.get(account.id)
        debit = item.debit if item else ZERO
        credit = item.credit if item else ZERO
        normal = debit - credit
        if account.kind in (
            models.CashbookAccountKind.LIABILITY,
            models.CashbookAccountKind.EQUITY,
            models.CashbookAccountKind.INCOME,
        ):
            normal = -normal
        result.append(
            schemas.CashbookAccountBalanceOut(
                **_account_out(account).model_dump(),
                debit=debit,
                credit=credit,
                balance=normal,
            )
        )
    return result


@router.post(
    "/accounts",
    response_model=schemas.CashbookAccountOut,
    status_code=201,
)
def create_account(
    payload: schemas.CashbookAccountCreate,
    request: Request,
    current_user: models.User = Depends(require_permission("accounting.adjust")),
    db: Session = Depends(get_db),
):
    exists = (
        db.query(models.CashbookAccount)
        .filter(models.CashbookAccount.code == payload.code)
        .first()
    )
    if exists is not None:
        raise HTTPException(
            status_code=409, detail=f"Account code {payload.code} is already in use"
        )
    account = models.CashbookAccount(
        code=payload.code,
        name=payload.name,
        kind=payload.kind,
        description=payload.description,
    )
    db.add(account)
    db.commit()
    db.refresh(account)
    audit_service.log_event(
        db,
        actor=current_user,
        event_type="cashbook.account_created",
        action="create",
        entity_type="cashbook_account",
        entity_id=str(account.id),
        new_values={
            "code": account.code,
            "name": account.name,
            "kind": account.kind.value,
        },
        request=request,
    )
    return account


@router.patch("/accounts/{account_id}", response_model=schemas.CashbookAccountOut)
def update_account(
    account_id: uuid.UUID,
    payload: schemas.CashbookAccountUpdate,
    request: Request,
    current_user: models.User = Depends(require_permission("accounting.adjust")),
    db: Session = Depends(get_db),
):
    account = db.query(models.CashbookAccount).filter(models.CashbookAccount.id == account_id).first()
    if account is None:
        raise HTTPException(status_code=404, detail="Account not found")

    changes = payload.model_dump(exclude_unset=True)
    if changes.get("is_active") is False:
        if account.system_key:
            raise HTTPException(
                status_code=400,
                detail="A system account is required by automatic postings and cannot be deactivated",
            )
        ledger = cashbook.account_ledger(db, account)
        if ledger.closing_balance != ZERO:
            raise HTTPException(
                status_code=400,
                detail="This account still carries a balance and cannot be deactivated",
            )

    previous = {
        "name": account.name,
        "description": account.description,
        "is_active": account.is_active,
    }
    for field, value in changes.items():
        setattr(account, field, value)
    db.commit()
    db.refresh(account)
    audit_service.log_event(
        db,
        actor=current_user,
        event_type="cashbook.account_updated",
        action="update",
        entity_type="cashbook_account",
        entity_id=str(account.id),
        previous_values=previous,
        new_values=changes,
        request=request,
    )
    return account


# ---------------------------------------------------------------------------
# Journal
# ---------------------------------------------------------------------------

@router.get("/entries", response_model=schemas.CashbookEntryPageOut)
def list_entries(
    start: Optional[date] = Query(default=None),
    end: Optional[date] = Query(default=None),
    account_id: Optional[uuid.UUID] = Query(default=None),
    source: Optional[models.CashbookEntrySource] = Query(default=None),
    q: Optional[str] = Query(default=None, max_length=120),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    current_user: models.User = Depends(require_permission("accounting.view")),
    db: Session = Depends(get_db),
):
    query = db.query(models.CashbookEntry)
    if start is not None:
        query = query.filter(models.CashbookEntry.entry_date >= start)
    if end is not None:
        query = query.filter(models.CashbookEntry.entry_date <= end)
    if source is not None:
        query = query.filter(models.CashbookEntry.source == source)
    if account_id is not None:
        query = query.filter(
            models.CashbookEntry.id.in_(
                db.query(models.CashbookLine.entry_id).filter(
                    models.CashbookLine.account_id == account_id
                )
            )
        )
    if q and q.strip():
        term = f"%{q.strip()}%"
        query = query.filter(
            or_(
                models.CashbookEntry.narration.ilike(term),
                models.CashbookEntry.reference.ilike(term),
            )
        )

    total = query.count()
    entries = (
        query.options(
            joinedload(models.CashbookEntry.lines).joinedload(
                models.CashbookLine.account
            )
        )
        .order_by(
            models.CashbookEntry.entry_date.desc(),
            models.CashbookEntry.created_at.desc(),
        )
        .offset(skip)
        .limit(limit)
        .all()
    )
    return schemas.CashbookEntryPageOut(
        items=[_entry_out(entry) for entry in entries],
        total=total,
        skip=skip,
        limit=limit,
    )


@router.post("/opening", response_model=schemas.CashbookEntryOut, status_code=201)
def post_opening(
    payload: schemas.CashbookOpeningCreate,
    request: Request,
    current_user: models.User = Depends(require_permission("accounting.post")),
    db: Session = Depends(get_db),
):
    if payload.as_of > date.today():
        raise HTTPException(status_code=400, detail="Opening balances cannot be dated in the future")
    try:
        entry = cashbook.post_opening(
            db,
            as_of=payload.as_of,
            lines=_resolve_lines(db, payload.lines),
            actor_id=current_user.id,
        )
    except cashbook.CashbookError as exc:
        raise _http(exc)
    if payload.note:
        entry.narration = payload.note[:255]
    db.commit()
    entry = _cashbook_entry_or_404(db, entry.id)
    audit_service.log_event(
        db,
        actor=current_user,
        event_type="cashbook.opening_posted",
        action="create",
        entity_type="cashbook_entry",
        entity_id=str(entry.id),
        new_values={
            "as_of": payload.as_of.isoformat(),
            "lines": [
                {
                    "account_id": str(line.account_id),
                    "debit": str(line.debit),
                    "credit": str(line.credit),
                }
                for line in payload.lines
            ],
        },
        request=request,
    )
    return _entry_out(entry)


@router.post("/entries", response_model=schemas.CashbookEntryOut, status_code=201)
def create_entry(
    payload: schemas.CashbookEntryCreate,
    request: Request,
    current_user: models.User = Depends(require_permission("accounting.post")),
    db: Session = Depends(get_db),
):
    if payload.entry_date > date.today():
        raise HTTPException(status_code=400, detail="An entry cannot be dated in the future")
    try:
        cashbook.require_open_books(db)
        entry = cashbook.post(
            db,
            entry_date=payload.entry_date,
            narration=payload.narration,
            reference=payload.reference,
            lines=_resolve_lines(db, payload.lines),
            source=models.CashbookEntrySource.MANUAL,
            actor_id=current_user.id,
        )
    except cashbook.CashbookError as exc:
        raise _http(exc)
    db.commit()
    entry = _cashbook_entry_or_404(db, entry.id)
    audit_service.log_event(
        db,
        actor=current_user,
        event_type="cashbook.entry_posted",
        action="create",
        entity_type="cashbook_entry",
        entity_id=str(entry.id),
        new_values={
            "entry_date": payload.entry_date.isoformat(),
            "narration": entry.narration,
            "lines": [
                {
                    "account_id": str(line.account_id),
                    "debit": str(line.debit),
                    "credit": str(line.credit),
                }
                for line in payload.lines
            ],
        },
        request=request,
    )
    return _entry_out(entry)


@router.post("/entries/{entry_id}/reverse", response_model=schemas.CashbookEntryOut, status_code=201)
def reverse_entry(
    entry_id: uuid.UUID,
    payload: schemas.CashbookReversalRequest,
    request: Request,
    current_user: models.User = Depends(require_permission("accounting.reverse")),
    db: Session = Depends(get_db),
):
    entry = _cashbook_entry_or_404(db, entry_id)
    try:
        reversal = cashbook.reverse(
            db,
            entry,
            reason=payload.reason,
            actor_id=current_user.id,
            entry_date=payload.entry_date,
        )
    except cashbook.CashbookError as exc:
        raise _http(exc)
    db.commit()
    reversal = _cashbook_entry_or_404(db, reversal.id)
    audit_service.log_event(
        db,
        actor=current_user,
        event_type="cashbook.entry_reversed",
        action="reverse",
        entity_type="cashbook_entry",
        entity_id=str(entry_id),
        new_values={
            "reversal_entry_id": str(reversal.id),
            "reason": payload.reason,
        },
        request=request,
    )
    return _entry_out(reversal)


# ---------------------------------------------------------------------------
# Period locks
# ---------------------------------------------------------------------------

@router.get("/period-locks", response_model=List[schemas.CashbookPeriodLockOut])
def list_locks(
    current_user: models.User = Depends(require_permission("accounting.view")),
    db: Session = Depends(get_db),
):
    return cashbook.period_locks(db)


@router.post(
    "/period-locks",
    response_model=schemas.CashbookPeriodLockOut,
    status_code=201,
)
def lock_month(
    payload: schemas.CashbookPeriodLockRequest,
    request: Request,
    current_user: models.User = Depends(require_permission("accounting.reconcile")),
    db: Session = Depends(get_db),
):
    try:
        lock = cashbook.lock_period(
            db,
            payload.period_start,
            actor=current_user,
            note=payload.note,
        )
    except cashbook.CashbookError as exc:
        raise _http(exc)
    db.commit()
    db.refresh(lock)
    audit_service.log_event(
        db,
        actor=current_user,
        event_type="cashbook.period_locked",
        action="lock",
        entity_type="cashbook_period",
        entity_id=lock.period_start.isoformat(),
        new_values={"note": lock.note},
        request=request,
    )
    return lock


@router.delete("/period-locks/{period_start}", status_code=204)
def unlock_month(
    period_start: date,
    request: Request,
    current_user: models.User = Depends(require_permission("accounting.reconcile")),
    db: Session = Depends(get_db),
):
    try:
        cashbook.unlock_period(db, period_start)
    except cashbook.CashbookError as exc:
        raise _http(exc)
    db.commit()
    audit_service.log_event(
        db,
        actor=current_user,
        event_type="cashbook.period_unlocked",
        action="unlock",
        entity_type="cashbook_period",
        entity_id=period_start.isoformat(),
        request=request,
    )
    return None


# ---------------------------------------------------------------------------
# Reports
# ---------------------------------------------------------------------------

def _movement_rows(rows) -> List[schemas.CashbookMovementRowOut]:
    return [
        schemas.CashbookMovementRowOut(
            account_id=row.account.id,
            code=row.account.code,
            name=row.account.name,
            amount=row.amount,
        )
        for row in rows
    ]


@router.get("/reports/trial-balance", response_model=schemas.CashbookTrialBalanceOut)
def trial_balance(
    as_of: Optional[date] = Query(default=None),
    current_user: models.User = Depends(_REPORT_ACCESS),
    db: Session = Depends(get_db),
):
    report = cashbook.trial_balance(db, as_of=as_of)
    return schemas.CashbookTrialBalanceOut(
        as_of=as_of,
        rows=[
            schemas.CashbookTrialBalanceRowOut(
                account_id=row.account.id,
                code=row.account.code,
                name=row.account.name,
                kind=row.account.kind,
                debit=row.debit,
                credit=row.credit,
            )
            for row in report.rows
        ],
        total_debit=report.total_debit,
        total_credit=report.total_credit,
        balanced=report.total_debit == report.total_credit,
    )


@router.get("/reports/income-expenditure", response_model=schemas.CashbookIncomeStatementOut)
def income_expenditure(
    start: Optional[date] = Query(default=None),
    end: Optional[date] = Query(default=None),
    current_user: models.User = Depends(_REPORT_ACCESS),
    db: Session = Depends(get_db),
):
    report = cashbook.income_statement(db, start=start, end=end)
    return schemas.CashbookIncomeStatementOut(
        start=start,
        end=end,
        income=_movement_rows(report.income),
        expenses=_movement_rows(report.expenses),
        total_income=report.total_income,
        total_expenses=report.total_expenses,
        surplus=report.surplus,
    )


@router.get("/reports/balance-sheet", response_model=schemas.CashbookBalanceSheetOut)
def balance_sheet(
    as_of: Optional[date] = Query(default=None),
    current_user: models.User = Depends(_REPORT_ACCESS),
    db: Session = Depends(get_db),
):
    report = cashbook.balance_sheet(db, as_of=as_of)
    return schemas.CashbookBalanceSheetOut(
        as_of=as_of,
        assets=_movement_rows(report.assets),
        liabilities=_movement_rows(report.liabilities),
        equity=_movement_rows(report.equity),
        surplus=report.surplus,
        total_assets=report.total_assets,
        total_liabilities=report.total_liabilities,
        total_equity=report.total_equity,
        balanced=report.total_assets == report.total_liabilities + report.total_equity,
    )


@router.get("/reports/cash-register", response_model=schemas.CashbookRegisterOut)
def cash_register(
    start: Optional[date] = Query(default=None),
    end: Optional[date] = Query(default=None),
    current_user: models.User = Depends(_REPORT_ACCESS),
    db: Session = Depends(get_db),
):
    rows = cashbook.cash_register(db, start=start, end=end)
    return schemas.CashbookRegisterOut(
        start=start,
        end=end,
        rows=[
            schemas.CashbookRegisterRowOut(
                entry_date=row.entry_date,
                narration=row.narration,
                reference=row.reference,
                account_code=row.account.code,
                account_name=row.account.name,
                amount=row.amount,
            )
            for row in rows
        ],
        total=sum((row.amount for row in rows), ZERO),
        cash_balance=_system_balance(db, cashbook.CASH, as_of=end),
        bank_balance=_system_balance(db, cashbook.BANK, as_of=end),
    )


@router.get("/reports/ledger/{account_id}", response_model=schemas.CashbookAccountLedgerOut)
def account_ledger(
    account_id: uuid.UUID,
    start: Optional[date] = Query(default=None),
    end: Optional[date] = Query(default=None),
    current_user: models.User = Depends(_REPORT_ACCESS),
    db: Session = Depends(get_db),
):
    account = db.query(models.CashbookAccount).filter(models.CashbookAccount.id == account_id).first()
    if account is None:
        raise HTTPException(status_code=404, detail="Account not found")
    ledger = cashbook.account_ledger(db, account, start=start, end=end)
    return schemas.CashbookAccountLedgerOut(
        account=_account_out(account),
        start=start,
        end=end,
        opening_balance=ledger.opening_balance,
        rows=[
            schemas.CashbookLedgerRowOut(
                entry_date=row.entry_date,
                narration=row.narration,
                reference=row.reference,
                debit=row.debit,
                credit=row.credit,
                balance=row.balance,
            )
            for row in ledger.rows
        ],
        closing_balance=ledger.closing_balance,
    )
