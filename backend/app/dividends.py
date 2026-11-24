"""Dividends: appropriating a closed year's surplus.

A dividend is not an expense. The year's income and expenditure are
closed into retained earnings first, then the pool, the reserve and the
honorarium are credited out of it. Member allocations become a liability
until a payout batch hands the money over.

The run is the snapshot: basis, rates, surplus window, each member's
basis and share are written once. Declaring is the point of no return --
it posts the closing and appropriation entries in the same transaction,
and the run is never recomputed afterwards. A later settings change can
therefore never rewrite a declared dividend.

Which members share is decided by the basis:

* ``net_savings_closing`` / ``declared_rate_on_savings`` -- the savings
  ledger balance at the year end;
* ``net_savings_average`` -- the mean month-end balance across the year;
* ``patronage`` -- interest collected from the member's loans during the
  year (at-source interest counts when the loan was disbursed in it);
* ``equal`` -- one share per eligible member;
* ``hybrid`` -- a weighted blend of savings and patronage shares;
* ``share_capital`` -- part of the policy vocabulary, but there is no
  share-capital ledger yet, so a run refuses it rather than guessing.
"""
import calendar
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from decimal import Decimal, ROUND_DOWN, ROUND_HALF_UP
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from sqlalchemy import func
from sqlalchemy.orm import Session

from . import cashbook, models

ZERO = Decimal("0.00")
CENT = Decimal("0.01")
ONE = Decimal("1")

DIVIDENDS_PAYABLE = "DIVIDENDS_PAYABLE"
HONORARIUM_PAYABLE = "HONORARIUM_PAYABLE"
WITHHOLDING_PAYABLE = "WITHHOLDING_PAYABLE"
RESERVE = "RESERVE"

MONEY_BASES = {
    models.DividendBasis.NET_SAVINGS_CLOSING,
    models.DividendBasis.NET_SAVINGS_AVERAGE,
    models.DividendBasis.DECLARED_RATE_ON_SAVINGS,
    models.DividendBasis.PATRONAGE,
}


class DividendError(Exception):
    """A guard the caller turns into an HTTP error, same shape as
    cashbook.CashbookError."""

    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def money(value) -> Decimal:
    return Decimal(value or 0).quantize(CENT, rounding=ROUND_HALF_UP)


def _settings(db: Session) -> models.Settings:
    settings = db.query(models.Settings).first()
    if settings is None:
        raise DividendError(409, "Configure the cooperative settings before declaring dividends.")
    return settings


def fiscal_year_bounds(settings: models.Settings, year: int) -> Tuple[date, date]:
    """A fiscal year is labelled by the calendar year it starts in."""
    month = int(settings.fiscal_year_start_month or 1)
    start = date(year, month, 1)
    if month == 1:
        end = date(year, 12, 31)
    else:
        end = date(year + 1, month - 1, calendar.monthrange(year + 1, month - 1)[1])
    return start, end


def _plus_month(day: date) -> date:
    if day.month == 12:
        return date(day.year + 1, 1, 1)
    return date(day.year, day.month + 1, 1)


def _month_end(day: date) -> date:
    return date(day.year, day.month, calendar.monthrange(day.year, day.month)[1])


def _minus_months(day: date, months: int) -> date:
    if months <= 0:
        return day
    total = day.year * 12 + (day.month - 1) - months
    year, month = divmod(total, 12)
    month += 1
    return date(year, month, min(day.day, calendar.monthrange(year, month)[1]))


def _end_of_day(day: date) -> datetime:
    return datetime.combine(day, time(23, 59, 59, 999999))


# ---------------------------------------------------------------------------
# Fiscal window
# ---------------------------------------------------------------------------

def previous_declared_run(db: Session, year: int) -> Optional[models.DividendRun]:
    return (
        db.query(models.DividendRun)
        .filter(
            models.DividendRun.fiscal_year < year,
            models.DividendRun.status.in_(
                [models.DividendRunStatus.DECLARED, models.DividendRunStatus.PAID]
            ),
        )
        .order_by(models.DividendRun.fiscal_year.desc())
        .first()
    )


def _window(
    db: Session, settings: models.Settings, year: int
) -> Tuple[date, date, Optional[models.DividendRun]]:
    """The surplus window must follow the last declared year, or the
    surplus would double-count (or miss) a year."""
    start, end = fiscal_year_bounds(settings, year)
    previous = previous_declared_run(db, year)
    if previous is not None:
        if previous.fiscal_year != year - 1:
            raise DividendError(
                409,
                f"Declare fiscal year {previous.fiscal_year + 1} first: dividends are declared "
                "one year at a time.",
            )
        if previous.period_end + timedelta(days=1) != start:
            raise DividendError(
                409,
                "The fiscal year start month changed after the last declaration. Restore the "
                "previous start month or start a new sequence before declaring again.",
            )
        return start, end, previous

    # No year has been closed yet. Income and expenditure from earlier
    # years would otherwise be swept into this run's surplus.
    kinds = (
        models.CashbookAccountKind.INCOME,
        models.CashbookAccountKind.EXPENSE,
    )
    earlier = (
        db.query(models.CashbookEntry.id)
        .join(models.CashbookLine, models.CashbookLine.entry_id == models.CashbookEntry.id)
        .join(models.CashbookAccount, models.CashbookAccount.id == models.CashbookLine.account_id)
        .filter(
            models.CashbookEntry.entry_date < start,
            models.CashbookEntry.source != models.CashbookEntrySource.YEAR_CLOSE,
            models.CashbookAccount.kind.in_(kinds),
        )
        .first()
    )
    if earlier is not None:
        raise DividendError(
            409,
            "This book has income or expenditure dated before the year starts. Declare the "
            "earlier fiscal year first, or correct those postings.",
        )
    return start, end, None


# ---------------------------------------------------------------------------
# Basis
# ---------------------------------------------------------------------------

def _savings_balances(
    db: Session, *, end: date, month_ends: Optional[List[date]] = None
) -> Dict[uuid.UUID, Decimal]:
    """Closing balance, or the mean of the month-end balances, from the
    append-only savings ledger. Reversals and exits are debits."""
    rows = (
        db.query(
            models.SavingsEntry.member_id,
            models.SavingsEntry.entry_type,
            models.SavingsEntry.amount,
            models.SavingsEntry.posted_at,
        )
        .filter(
            (models.SavingsEntry.posted_at.is_(None))
            | (models.SavingsEntry.posted_at <= _end_of_day(end))
        )
        .order_by(models.SavingsEntry.posted_at.asc())
        .all()
    )
    by_member: Dict[uuid.UUID, List[Tuple[datetime, Decimal]]] = {}
    for member_id, entry_type, amount, posted_at in rows:
        delta = money(amount)
        if entry_type != models.SavingsEntryType.CONTRIBUTION:
            delta = -delta
        when = posted_at or datetime.min
        by_member.setdefault(member_id, []).append((when, delta))

    result: Dict[uuid.UUID, Decimal] = {}
    for member_id, movements in by_member.items():
        running = ZERO
        if month_ends is None:
            for _, delta in movements:
                running += delta
            result[member_id] = running
            continue

        months: List[Decimal] = []
        index = 0
        for month_end in month_ends:
            cutoff = _end_of_day(month_end)
            while index < len(movements) and movements[index][0] <= cutoff:
                running += movements[index][1]
                index += 1
            months.append(running)
        if months:
            result[member_id] = (sum(months, ZERO) / Decimal(len(months))).quantize(
                CENT, rounding=ROUND_HALF_UP
            )
    return result


def _patronage_interest(
    db: Session, *, start: date, end: date
) -> Dict[uuid.UUID, Decimal]:
    """Interest collected from each member's loans during the window.

    At-source interest is earned when the loan is disbursed, so only a
    loan disbursed inside the window counts. Spread interest is collected
    with each payment, so the year gets the proportional share of what
    was actually collected -- repayments and payroll deduction lines.
    """
    collected: Dict[uuid.UUID, Decimal] = {}

    repayments = (
        db.query(models.LoanRepayment.loan_id, func.coalesce(func.sum(models.LoanRepayment.amount_claimed), 0))
        .filter(
            models.LoanRepayment.status == models.RepaymentVerificationStatus.VERIFIED,
            models.LoanRepayment.payment_month.isnot(None),
            models.LoanRepayment.payment_month >= start,
            models.LoanRepayment.payment_month <= end,
        )
        .group_by(models.LoanRepayment.loan_id)
        .all()
    )
    for loan_id, amount in repayments:
        collected[loan_id] = collected.get(loan_id, ZERO) + money(amount)

    deductions = (
        db.query(
            models.PayrollDeductionLine.loan_id,
            func.coalesce(func.sum(models.PayrollDeductionLine.amount), 0),
        )
        .join(models.PayrollDeduction, models.PayrollDeduction.id == models.PayrollDeductionLine.deduction_id)
        .filter(
            models.PayrollDeduction.status == models.PayrollDeductionStatus.CONFIRMED,
            models.PayrollDeduction.deduction_month >= start,
            models.PayrollDeduction.deduction_month <= end,
            models.PayrollDeductionLine.loan_id.isnot(None),
            models.PayrollDeductionLine.category.in_(
                [
                    models.PayrollDeductionLineCategory.LOAN_REPAYMENT,
                    models.PayrollDeductionLineCategory.LOAN_ARREARS,
                ]
            ),
        )
        .group_by(models.PayrollDeductionLine.loan_id)
        .all()
    )
    for loan_id, amount in deductions:
        collected[loan_id] = collected.get(loan_id, ZERO) + money(amount)

    loans = (
        db.query(models.Loan)
        .filter(
            models.Loan.interest_amount > 0,
            models.Loan.disbursement_date <= end,
        )
        .all()
    )
    interest: Dict[uuid.UUID, Decimal] = {}
    for loan in loans:
        amount = ZERO
        if loan.interest_mode in (None, models.InterestDeductionMode.AT_SOURCE):
            if loan.disbursement_date >= start:
                amount = money(loan.interest_amount)
        else:
            total = money(loan.total_repayable)
            paid = collected.get(loan.id, ZERO)
            if total > ZERO and paid > ZERO:
                portion = money(loan.interest_amount) * min(paid, total) / total
                amount = money(portion)
        if amount > ZERO:
            interest[loan.member_id] = interest.get(loan.member_id, ZERO) + amount
    return interest


@dataclass
class AllocationPreview:
    member_id: uuid.UUID
    psn: str
    name: str
    bank_name: Optional[str]
    account_number: Optional[str]
    basis_amount: Decimal
    share_ratio: Decimal
    gross_amount: Decimal = ZERO
    withholding_amount: Decimal = ZERO
    net_amount: Decimal = ZERO
    rounding_adjustment: Decimal = ZERO


@dataclass
class DividendComputation:
    fiscal_year: int
    period_start: date
    period_end: date
    basis: models.DividendBasis
    pool_mode: models.DividendPoolMode
    surplus: Decimal
    reserve_pct: Decimal
    reserve_amount: Decimal
    honorarium_pct: Decimal
    honorarium_amount: Decimal
    payout_pct: Decimal
    pool_amount: Decimal
    declared_rate_pct: Optional[Decimal]
    fixed_pool_amount: Optional[Decimal]
    hybrid_savings_pct: Decimal
    withholding_pct: Decimal
    rounding: models.DividendRounding
    min_membership_months: int
    include_exited: bool
    closed_income_total: Decimal
    closed_expense_total: Decimal
    total_basis_amount: Decimal
    total_gross: Decimal
    total_withholding: Decimal
    total_net: Decimal
    rounding_residual: Decimal
    allocations: List[AllocationPreview] = field(default_factory=list)

    @property
    def eligible_member_count(self) -> int:
        return len(self.allocations)


def _month_ends(start: date, end: date) -> List[date]:
    months: List[date] = []
    cursor = date(start.year, start.month, 1)
    while cursor <= end:
        months.append(min(_month_end(cursor), end))
        cursor = _plus_month(cursor)
    return months


def _eligible_members(
    db: Session, settings: models.Settings, end: date
) -> List[models.Member]:
    members = (
        db.query(models.Member)
        .filter(models.Member.status == models.MemberStatus.FINANCIAL)
        .order_by(models.Member.psn.asc())
        .all()
    )
    cutoff = _minus_months(end, int(settings.dividend_min_membership_months or 0))
    eligible: List[models.Member] = []
    for member in members:
        if (
            member.membership_exit_date is not None
            and member.membership_exit_date <= end
            and not settings.dividend_include_exited
        ):
            continue
        if member.created_at is not None and member.created_at.date() > cutoff:
            continue
        eligible.append(member)
    return eligible


def _round_allocations(
    rows: List[AllocationPreview],
    *,
    pool: Decimal,
    unit: Decimal,
) -> Tuple[Decimal, Decimal]:
    """Split ``pool`` to the cent (or whole naira), returning the rounding
    residual and total gross. The largest-remainder method keeps the rows
    summing to the allocatable pool exactly; ties go by PSN so two runs
    over the same data always produce the same figures."""
    if not rows or pool <= ZERO:
        return ZERO, ZERO
    raw = {row.member_id: pool * row.share_ratio for row in rows}
    rounded = {
        member_id: amount.quantize(unit, rounding=ROUND_HALF_UP)
        for member_id, amount in raw.items()
    }
    target = pool.quantize(unit, rounding=ROUND_DOWN)
    difference = target - sum(rounded.values(), ZERO)
    units = int(abs(difference) / unit)

    if units:
        # Positive residual: add a unit to the rows with the largest
        # fractional remainder. Negative: take it back from the rows that
        # were rounded up the most. PSN breaks ties so runs are repeatable.
        def remainder(row: AllocationPreview) -> Decimal:
            if difference > ZERO:
                return raw[row.member_id] - raw[row.member_id].quantize(unit, rounding=ROUND_DOWN)
            return raw[row.member_id].quantize(unit, rounding=ROUND_HALF_UP) - raw[row.member_id]

        order = sorted(
            rows,
            key=lambda row: (-remainder(row) if difference > ZERO else remainder(row), row.psn),
        )
        step = unit if difference > ZERO else -unit
        index = 0
        passes = 0
        while units > 0 and order and passes < len(order) * 4:
            row = order[index % len(order)]
            if rounded[row.member_id] + step >= ZERO:
                rounded[row.member_id] += step
                units -= 1
            index += 1
            passes += 1

    total_gross = ZERO
    for row in rows:
        final = rounded[row.member_id]
        row.rounding_adjustment = final - raw[row.member_id].quantize(unit, rounding=ROUND_HALF_UP)
        row.gross_amount = final
        total_gross += final
    return pool - total_gross, total_gross


def compute(
    db: Session, fiscal_year: int, *, settings: Optional[models.Settings] = None
) -> DividendComputation:
    settings = settings or _settings(db)
    if not settings.dividends_module_enabled:
        raise DividendError(403, "The Dividends module is disabled by an administrator.")
    if settings.dividend_basis == models.DividendBasis.NONE:
        raise DividendError(409, "Choose a dividend basis in Cooperative settings first.")
    if settings.dividend_basis == models.DividendBasis.SHARE_CAPITAL:
        raise DividendError(
            409,
            "Share capital has no member ledger yet, so it cannot be a dividend basis. "
            "Choose another basis in Cooperative settings.",
        )

    start, end, _ = _window(db, settings, fiscal_year)
    statement = cashbook.income_statement(db, start=start, end=end)
    surplus = money(statement.surplus)

    reserve_pct = money(settings.dividend_reserve_pct)
    honorarium_pct = money(settings.dividend_honorarium_pct)
    payout_pct = money(settings.dividend_payout_pct)

    eligible = _eligible_members(db, settings, end)
    basis = settings.dividend_basis

    if surplus <= ZERO:
        return DividendComputation(
            fiscal_year=fiscal_year,
            period_start=start,
            period_end=end,
            basis=basis,
            pool_mode=settings.dividend_pool_mode,
            surplus=surplus,
            reserve_pct=reserve_pct,
            reserve_amount=ZERO,
            honorarium_pct=honorarium_pct,
            honorarium_amount=ZERO,
            payout_pct=payout_pct,
            pool_amount=ZERO,
            declared_rate_pct=settings.dividend_declared_rate_pct,
            fixed_pool_amount=settings.dividend_fixed_pool_amount,
            hybrid_savings_pct=money(settings.dividend_hybrid_savings_pct),
            withholding_pct=money(settings.dividend_withholding_pct),
            rounding=settings.dividend_rounding,
            min_membership_months=int(settings.dividend_min_membership_months or 0),
            include_exited=bool(settings.dividend_include_exited),
            closed_income_total=money(statement.total_income),
            closed_expense_total=money(statement.total_expenses),
            total_basis_amount=ZERO,
            total_gross=ZERO,
            total_withholding=ZERO,
            total_net=ZERO,
            rounding_residual=ZERO,
        )

    savings: Dict[uuid.UUID, Decimal] = {}
    if basis in (
        models.DividendBasis.NET_SAVINGS_CLOSING,
        models.DividendBasis.DECLARED_RATE_ON_SAVINGS,
        models.DividendBasis.HYBRID,
    ):
        savings = _savings_balances(db, end=end)
    elif basis == models.DividendBasis.NET_SAVINGS_AVERAGE:
        savings = _savings_balances(db, end=end, month_ends=_month_ends(start, end))

    patronage: Dict[uuid.UUID, Decimal] = {}
    if basis in (models.DividendBasis.PATRONAGE, models.DividendBasis.HYBRID):
        patronage = _patronage_interest(db, start=start, end=end)

    basis_amounts: Dict[uuid.UUID, Decimal] = {}
    if basis == models.DividendBasis.EQUAL:
        for member in eligible:
            basis_amounts[member.id] = ONE
    elif basis == models.DividendBasis.PATRONAGE:
        for member in eligible:
            amount = money(patronage.get(member.id, ZERO))
            if amount > ZERO:
                basis_amounts[member.id] = amount
    elif basis == models.DividendBasis.HYBRID:
        savings_total = sum((savings.get(m.id, ZERO) for m in eligible), ZERO)
        patronage_total = sum((patronage.get(m.id, ZERO) for m in eligible), ZERO)
        savings_weight = money(settings.dividend_hybrid_savings_pct) / Decimal("100")
        patronage_weight = ONE - savings_weight
        for member in eligible:
            share = ZERO
            if savings_total > ZERO:
                share += savings_weight * (savings.get(member.id, ZERO) / savings_total)
            if patronage_total > ZERO:
                share += patronage_weight * (patronage.get(member.id, ZERO) / patronage_total)
            score = share.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
            if score > ZERO:
                basis_amounts[member.id] = score
    else:
        for member in eligible:
            amount = money(savings.get(member.id, ZERO))
            if amount > ZERO:
                basis_amounts[member.id] = amount

    rows = [
        AllocationPreview(
            member_id=member.id,
            psn=member.psn,
            name=member.name,
            bank_name=member.bank_name,
            account_number=member.account_number,
            basis_amount=basis_amounts[member.id],
            share_ratio=ZERO,
        )
        for member in eligible
        if member.id in basis_amounts
    ]
    if not rows:
        raise DividendError(409, "No eligible member has a basis for this fiscal year's dividend.")
    total_basis = sum((row.basis_amount for row in rows), ZERO)
    for row in rows:
        row.share_ratio = (row.basis_amount / total_basis).quantize(
            Decimal("0.000000000001"), rounding=ROUND_HALF_UP
        )

    reserve_amount = money(surplus * reserve_pct / Decimal("100"))
    honorarium_amount = money(surplus * honorarium_pct / Decimal("100"))
    distributable = surplus - reserve_amount - honorarium_amount

    pool_mode = settings.dividend_pool_mode
    if pool_mode == models.DividendPoolMode.NET_INCOME_SHARE:
        split = reserve_pct + honorarium_pct + payout_pct
        if abs(split - Decimal("100")) > Decimal("0.01"):
            raise DividendError(
                409,
                "The reserve, honorarium and payout percentages must add up to 100 before a "
                "dividend can be computed.",
            )
        pool = money(surplus * payout_pct / Decimal("100"))
    elif pool_mode == models.DividendPoolMode.SAVINGS_PERCENT:
        rate = settings.dividend_declared_rate_pct
        if rate is None:
            raise DividendError(
                409, "Set the declared dividend rate before computing a savings-percentage pool."
            )
        pool = money(total_basis * money(rate) / Decimal("100"))
    else:
        if settings.dividend_fixed_pool_amount is None:
            raise DividendError(409, "Set the fixed dividend pool amount before computing a run.")
        pool = money(settings.dividend_fixed_pool_amount)

    if pool <= ZERO:
        raise DividendError(409, "The dividend pool is zero; there is nothing to allocate.")
    if pool > distributable:
        raise DividendError(
            409,
            f"The pool ({pool}) exceeds the distributable surplus ({distributable}) after "
            "reserve and honorarium.",
        )

    unit = CENT if settings.dividend_rounding == models.DividendRounding.TWO_DP else Decimal("1")
    residual, total_gross = _round_allocations(rows, pool=pool, unit=unit)

    withholding_pct = money(settings.dividend_withholding_pct)
    total_withholding = ZERO
    total_net = ZERO
    for row in rows:
        row.withholding_amount = money(row.gross_amount * withholding_pct / Decimal("100"))
        row.net_amount = row.gross_amount - row.withholding_amount
        total_withholding += row.withholding_amount
        total_net += row.net_amount

    return DividendComputation(
        fiscal_year=fiscal_year,
        period_start=start,
        period_end=end,
        basis=basis,
        pool_mode=pool_mode,
        surplus=surplus,
        reserve_pct=reserve_pct,
        reserve_amount=reserve_amount,
        honorarium_pct=honorarium_pct,
        honorarium_amount=honorarium_amount,
        payout_pct=payout_pct,
        pool_amount=pool,
        declared_rate_pct=settings.dividend_declared_rate_pct,
        fixed_pool_amount=settings.dividend_fixed_pool_amount,
        hybrid_savings_pct=money(settings.dividend_hybrid_savings_pct),
        withholding_pct=withholding_pct,
        rounding=settings.dividend_rounding,
        min_membership_months=int(settings.dividend_min_membership_months or 0),
        include_exited=bool(settings.dividend_include_exited),
        closed_income_total=money(statement.total_income),
        closed_expense_total=money(statement.total_expenses),
        total_basis_amount=total_basis,
        total_gross=total_gross,
        total_withholding=total_withholding,
        total_net=total_net,
        rounding_residual=residual,
        allocations=rows,
    )


# ---------------------------------------------------------------------------
# Drafts
# ---------------------------------------------------------------------------

def _apply(db: Session, run: models.DividendRun, computation: DividendComputation) -> None:
    run.period_start = computation.period_start
    run.period_end = computation.period_end
    run.basis = computation.basis
    run.pool_mode = computation.pool_mode
    run.surplus = computation.surplus
    run.reserve_pct = computation.reserve_pct
    run.reserve_amount = computation.reserve_amount
    run.honorarium_pct = computation.honorarium_pct
    run.honorarium_amount = computation.honorarium_amount
    run.payout_pct = computation.payout_pct
    run.pool_amount = computation.pool_amount
    run.declared_rate_pct = computation.declared_rate_pct
    run.fixed_pool_amount = computation.fixed_pool_amount
    run.hybrid_savings_pct = computation.hybrid_savings_pct
    run.withholding_pct = computation.withholding_pct
    run.rounding = computation.rounding
    run.min_membership_months = computation.min_membership_months
    run.include_exited = computation.include_exited
    run.closed_income_total = computation.closed_income_total
    run.closed_expense_total = computation.closed_expense_total
    run.total_basis_amount = computation.total_basis_amount
    run.total_gross = computation.total_gross
    run.total_withholding = computation.total_withholding
    run.total_net = computation.total_net
    run.rounding_residual = computation.rounding_residual
    run.eligible_member_count = len(computation.allocations)

    had_allocations = bool(run.allocations)
    for allocation in list(run.allocations):
        run.allocations.remove(allocation)
    if had_allocations:
        # One row per member, so the old rows must leave the database
        # before the replacements arrive.
        db.flush()
    for row in computation.allocations:
        run.allocations.append(
            models.DividendAllocation(
                member_id=row.member_id,
                basis_amount=row.basis_amount,
                share_ratio=row.share_ratio,
                gross_amount=row.gross_amount,
                withholding_amount=row.withholding_amount,
                net_amount=row.net_amount,
                rounding_adjustment=row.rounding_adjustment,
            )
        )


def create_or_update_draft(
    db: Session,
    *,
    fiscal_year: int,
    actor_id: Optional[uuid.UUID] = None,
    note: Optional[str] = None,
) -> models.DividendRun:
    run = (
        db.query(models.DividendRun)
        .filter(models.DividendRun.fiscal_year == fiscal_year)
        .first()
    )
    if run is not None and run.status != models.DividendRunStatus.DRAFT:
        raise DividendError(409, f"Fiscal year {fiscal_year} has already been declared.")
    computation = compute(db, fiscal_year)
    if run is None:
        run = models.DividendRun(
            fiscal_year=fiscal_year,
            basis=computation.basis,
            pool_mode=computation.pool_mode,
            created_by_user_id=actor_id,
        )
        db.add(run)
    _apply(db, run, computation)
    if note is not None:
        run.note = note.strip() or None
    db.flush()
    return run


def delete_draft(db: Session, run: models.DividendRun) -> None:
    if run.status != models.DividendRunStatus.DRAFT:
        raise DividendError(409, "Only a draft can be deleted; a declared dividend is history.")
    db.delete(run)
    db.flush()


# ---------------------------------------------------------------------------
# Declaration
# ---------------------------------------------------------------------------

def _same(a: Decimal, b: Decimal) -> bool:
    return money(a) == money(b)


def _post_year_close(
    db: Session,
    run: models.DividendRun,
    *,
    actor_id: Optional[uuid.UUID],
) -> None:
    statement = cashbook.income_statement(db, start=run.period_start, end=run.period_end)
    retained = cashbook.system_account(db, "RETAINED_EARNINGS")
    lines: List[Tuple[object, Decimal, Decimal]] = []
    for row in statement.income:
        # A net debit on an income account (a refund) closes on the
        # opposite side; the movement is signed, the line is not.
        if row.amount >= ZERO:
            lines.append((row.account, row.amount, ZERO))
        else:
            lines.append((row.account, ZERO, -row.amount))
    for row in statement.expenses:
        if row.amount >= ZERO:
            lines.append((row.account, ZERO, row.amount))
        else:
            lines.append((row.account, -row.amount, ZERO))
    surplus = money(statement.surplus)
    if surplus > ZERO:
        lines.append((retained, ZERO, surplus))
    elif surplus < ZERO:
        lines.append((retained, -surplus, ZERO))
    if len(lines) < 2:
        return
    cashbook.post(
        db,
        entry_date=run.period_end,
        narration=f"Close fiscal year {run.fiscal_year}",
        lines=lines,
        source=models.CashbookEntrySource.YEAR_CLOSE,
        source_id=run.id,
        actor_id=actor_id,
    )


def declare(
    db: Session,
    run: models.DividendRun,
    *,
    actor_id: Optional[uuid.UUID],
    declared_on: Optional[date] = None,
) -> models.DividendRun:
    if run.status != models.DividendRunStatus.DRAFT:
        raise DividendError(409, "This dividend has already been declared.")
    cashbook.require_open_books(db)
    declared_on = declared_on or date.today()
    if declared_on > date.today():
        raise DividendError(400, "A dividend cannot be declared in the future.")
    if declared_on < run.period_end:
        raise DividendError(400, "A dividend is declared after its fiscal year ends.")

    fresh = compute(db, run.fiscal_year)
    if (
        not _same(fresh.surplus, run.surplus)
        or not _same(fresh.total_gross, run.total_gross)
        or money(fresh.total_basis_amount) != money(run.total_basis_amount)
        or fresh.eligible_member_count != run.eligible_member_count
        or fresh.basis != run.basis
    ):
        raise DividendError(
            409,
            "The figures changed since this draft was computed. Refresh the draft and review "
            "it before declaring.",
        )

    accounts = cashbook.system_accounts(
        db, "RETAINED_EARNINGS", RESERVE, HONORARIUM_PAYABLE, DIVIDENDS_PAYABLE
    )
    distribution = money(
        money(run.reserve_amount) + money(run.honorarium_amount) + money(run.total_gross)
    )
    retained_after_close = (
        cashbook.account_ledger(db, accounts["RETAINED_EARNINGS"], end=declared_on).closing_balance
        + money(run.surplus)
    )
    if distribution > retained_after_close:
        raise DividendError(
            409,
            "Retained earnings would not cover this distribution. Check earlier years' "
            "postings before declaring.",
        )

    _post_year_close(db, run, actor_id=actor_id)

    if distribution > ZERO:
        cashbook.post(
            db,
            entry_date=declared_on,
            narration=f"Dividend declared for {run.fiscal_year}",
            reference=f"dividend-{run.fiscal_year}",
            source=models.CashbookEntrySource.DIVIDEND_DECLARATION,
            source_id=run.id,
            actor_id=actor_id,
            lines=[
                (accounts["RETAINED_EARNINGS"], distribution, ZERO),
                (accounts[RESERVE], ZERO, money(run.reserve_amount)),
                (accounts[HONORARIUM_PAYABLE], ZERO, money(run.honorarium_amount)),
                (accounts[DIVIDENDS_PAYABLE], ZERO, money(run.total_gross)),
            ],
        )

    run.status = models.DividendRunStatus.DECLARED
    run.declared_on = declared_on
    run.declared_by_user_id = actor_id
    db.flush()
    return run


# ---------------------------------------------------------------------------
# Payouts
# ---------------------------------------------------------------------------

def record_payout(
    db: Session,
    run: models.DividendRun,
    *,
    paid_on: date,
    method: models.DividendPayoutMethod,
    reference: str,
    actor_id: Optional[uuid.UUID],
    allocation_ids: Optional[Sequence[uuid.UUID]] = None,
    note: Optional[str] = None,
) -> models.DividendPayout:
    if run.status != models.DividendRunStatus.DECLARED:
        raise DividendError(409, "Only a declared dividend with an unpaid balance can be paid.")
    cashbook.require_open_books(db)
    if paid_on > date.today():
        raise DividendError(400, "A payout cannot be dated in the future.")
    reference = (reference or "").strip()
    if not reference:
        raise DividendError(400, "A payment reference is required.")

    settings = _settings(db)
    policy = settings.dividend_payment_method
    if policy == models.DividendPaymentPolicy.BANK and method != models.DividendPayoutMethod.BANK:
        raise DividendError(400, "The cooperative pays dividends from the bank.")
    if policy == models.DividendPaymentPolicy.CASH and method != models.DividendPayoutMethod.CASH:
        raise DividendError(400, "The cooperative pays dividends from cash.")

    query = db.query(models.DividendAllocation).filter(
        models.DividendAllocation.run_id == run.id,
        models.DividendAllocation.payout_id.is_(None),
    )
    if allocation_ids is not None:
        wanted = list({uuid.UUID(str(item)) for item in allocation_ids})
        if not wanted:
            raise DividendError(400, "Select at least one unpaid allocation.")
        query = query.filter(models.DividendAllocation.id.in_(wanted))
    pending = query.all()
    if not pending:
        raise DividendError(409, "Every allocation in this run has already been paid.")
    if allocation_ids is not None and len(pending) != len(set(allocation_ids)):
        raise DividendError(409, "Some selected allocations are not unpaid members of this run.")

    gross = sum((money(row.gross_amount) for row in pending), ZERO)
    withholding = sum((money(row.withholding_amount) for row in pending), ZERO)
    net = sum((money(row.net_amount) for row in pending), ZERO)
    if net <= ZERO:
        raise DividendError(409, "The selected allocations have nothing to pay out.")

    paid_from = cashbook.CASH if method == models.DividendPayoutMethod.CASH else cashbook.BANK
    accounts = cashbook.system_accounts(db, DIVIDENDS_PAYABLE, paid_from)
    if withholding > ZERO:
        accounts.update(cashbook.system_accounts(db, WITHHOLDING_PAYABLE))

    payout = models.DividendPayout(
        run_id=run.id,
        paid_on=paid_on,
        method=method,
        reference=reference,
        amount=net,
        note=(note or "").strip() or None,
        created_by_user_id=actor_id,
    )
    db.add(payout)
    db.flush()

    entry_lines: List[Tuple[object, Decimal, Decimal]] = [
        (accounts[DIVIDENDS_PAYABLE], gross, ZERO),
        (accounts[paid_from], ZERO, net),
    ]
    if withholding > ZERO:
        entry_lines.append((accounts[WITHHOLDING_PAYABLE], ZERO, withholding))

    cashbook.post(
        db,
        entry_date=paid_on,
        narration=f"Dividend payout {run.fiscal_year}",
        reference=reference,
        source=models.CashbookEntrySource.DIVIDEND_PAYMENT,
        source_id=payout.id,
        actor_id=actor_id,
        lines=entry_lines,
    )

    for allocation in pending:
        allocation.payout_id = payout.id
    # SessionLocal has autoflush off, so the count below only sees the
    # assignments once they're flushed.
    db.flush()

    remaining = (
        db.query(models.DividendAllocation)
        .filter(
            models.DividendAllocation.run_id == run.id,
            models.DividendAllocation.payout_id.is_(None),
        )
        .count()
    )
    if remaining == 0:
        run.status = models.DividendRunStatus.PAID
    db.flush()
    return payout


# ---------------------------------------------------------------------------
# Reporting helpers
# ---------------------------------------------------------------------------

def manifest(run: models.DividendRun) -> List[dict]:
    rows = []
    for allocation in sorted(run.allocations, key=lambda row: row.member.psn if row.member else ""):
        member = allocation.member
        rows.append(
            {
                "psn": member.psn if member else "",
                "name": member.name if member else "",
                "bank_name": member.bank_name if member else None,
                "account_number": member.account_number if member else None,
                "gross_amount": money(allocation.gross_amount),
                "withholding_amount": money(allocation.withholding_amount),
                "net_amount": money(allocation.net_amount),
                "payout_id": allocation.payout_id,
            }
        )
    return rows
