"""The cooperative's double-entry cashbook.

Every money movement gets a balanced journal entry: total debits equal
total credits, and a line sits on exactly one side. That is the one rule
the legacy workbook broke (it derived income and expense from the sign of
an amount on a single list), and it is why this book can produce a trial
balance that must foot to zero instead of a statement that only roughly
agrees.

Entries are immutable once posted. A mistake is corrected with a reversing
entry that names the original, so the history still shows what was posted
and by whom. A month is closed with a period lock; after that nothing may
be dated inside it, and corrections land in the open month.

Automatic postings run inside the same transaction as the money flow that
caused them (payroll confirmation, disbursement, repayment verification,
fee verification, exit settlement), so a confirmed movement can never
exist without its journal entry. They start only once the cooperative has
posted an opening journal -- a book cannot have activity before its
opening balances -- and they are skipped while the cashbook module is off.

Interest is recognised when the cooperative earns it, not when the charge
is computed:

* ``at_source`` loans collect the whole interest out of the principal, so
  it is income on the disbursement date;
* spread loans collect it with each repayment, so each collected amount
  carries its proportional share (``amount * interest / total_repayable``),
  and the final payment carries the exact remainder so rounding can never
  leave interest uncollected.
"""
import uuid
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, List, NamedTuple, Optional, Sequence, Tuple

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from . import models

ZERO = Decimal("0.00")
CENT = Decimal("0.01")

CASH = "CASH"
BANK = "BANK"
LOAN_RECEIVABLE = "LOAN_RECEIVABLE"
MEMBER_SAVINGS = "MEMBER_SAVINGS"
PAYOUT_PAYABLE = "PAYOUT_PAYABLE"
OTHER_DEDUCTIONS_PAYABLE = "OTHER_DEDUCTIONS_PAYABLE"
INTEREST_INCOME = "INTEREST_INCOME"
LOAN_FEE_INCOME = "LOAN_FEE_INCOME"


class CashbookError(Exception):
    """A guard the caller turns into an HTTP error, same shape as
    settlements.SettlementError."""

    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def money(value: Any) -> Decimal:
    return Decimal(value or 0).quantize(CENT, rounding=ROUND_HALF_UP)


def month_start(day: date) -> date:
    return date(day.year, day.month, 1)


def module_enabled(db: Session) -> bool:
    settings = db.query(models.Settings).first()
    return bool(settings is not None and settings.cashbook_module_enabled)


def opening_entry(db: Session) -> Optional[models.CashbookEntry]:
    return (
        db.query(models.CashbookEntry)
        .filter(models.CashbookEntry.source == models.CashbookEntrySource.OPENING)
        .order_by(models.CashbookEntry.created_at.asc())
        .first()
    )


def books_open(db: Session) -> bool:
    """Automatic postings wait for the opening journal: activity before
    an opening balance would double-count whatever the opening states."""
    if not module_enabled(db):
        return False
    return opening_entry(db) is not None


def require_open_books(db: Session) -> None:
    if not module_enabled(db):
        raise CashbookError(403, "The Cashbook module is disabled by an administrator.")
    if opening_entry(db) is None:
        raise CashbookError(
            409, "Post the opening balances before recording any other cashbook movement."
        )


# ---------------------------------------------------------------------------
# Chart of accounts
# ---------------------------------------------------------------------------

def system_accounts(db: Session, *keys: str) -> Dict[str, models.CashbookAccount]:
    rows = (
        db.query(models.CashbookAccount)
        .filter(models.CashbookAccount.system_key.in_(keys))
        .all()
    )
    found = {row.system_key: row for row in rows}
    missing = [key for key in keys if key not in found]
    if missing:
        raise CashbookError(
            409,
            "The chart of accounts is missing required accounts: "
            + ", ".join(missing)
            + ". Restore them before posting.",
        )
    return found


def system_account(db: Session, key: str) -> models.CashbookAccount:
    return system_accounts(db, key)[key]


# ---------------------------------------------------------------------------
# Period locks
# ---------------------------------------------------------------------------

def locked_period(db: Session, day: date) -> Optional[models.CashbookPeriodLock]:
    return (
        db.query(models.CashbookPeriodLock)
        .filter(models.CashbookPeriodLock.period_start == month_start(day))
        .first()
    )


def is_locked(db: Session, day: date) -> bool:
    return locked_period(db, day) is not None


def period_locks(db: Session) -> List[models.CashbookPeriodLock]:
    return (
        db.query(models.CashbookPeriodLock)
        .order_by(models.CashbookPeriodLock.period_start.desc())
        .all()
    )


def lock_period(
    db: Session,
    period_start: date,
    *,
    actor: Optional[models.User] = None,
    note: Optional[str] = None,
) -> models.CashbookPeriodLock:
    if period_start.day != 1:
        raise CashbookError(400, "A period must start on the first day of a month")
    if period_start > month_start(date.today()):
        raise CashbookError(400, "A future month cannot be locked")
    if locked_period(db, period_start) is not None:
        raise CashbookError(409, "That month is already locked")
    lock = models.CashbookPeriodLock(
        period_start=period_start,
        locked_by_user_id=actor.id if actor else None,
        locked_at=datetime.utcnow(),
        note=note,
    )
    db.add(lock)
    db.flush()
    return lock


def unlock_period(db: Session, period_start: date) -> None:
    lock = locked_period(db, period_start)
    if lock is None:
        raise CashbookError(404, "That month is not locked")
    db.delete(lock)
    db.flush()


# ---------------------------------------------------------------------------
# Journal posting
# ---------------------------------------------------------------------------

def _account_id(account: Any) -> uuid.UUID:
    if isinstance(account, models.CashbookAccount):
        if not account.is_active:
            raise CashbookError(
                400, f"Account {account.code} {account.name} is inactive and cannot be posted to"
            )
        return account.id
    return account


def post(
    db: Session,
    *,
    entry_date: date,
    narration: str,
    lines: Sequence[Tuple[Any, Decimal, Decimal]],
    source: models.CashbookEntrySource = models.CashbookEntrySource.MANUAL,
    source_id: Optional[uuid.UUID] = None,
    reference: Optional[str] = None,
    actor_id: Optional[uuid.UUID] = None,
    reverses_entry_id: Optional[uuid.UUID] = None,
    reversal_reason: Optional[str] = None,
) -> models.CashbookEntry:
    """Add a balanced entry. The caller commits.

    ``lines`` are ``(account, debit, credit)``; zero-amount lines are
    dropped so callers can pass a rule's full shape without branching.
    ``(source, source_id)`` is unique in the database: a repeated call for
    the same event returns the entry already posted instead of doubling
    the books.
    """
    if source_id is not None:
        existing = (
            db.query(models.CashbookEntry)
            .filter(
                models.CashbookEntry.source == source,
                models.CashbookEntry.source_id == source_id,
            )
            .first()
        )
        if existing is not None:
            return existing

    if locked_period(db, entry_date) is not None:
        raise CashbookError(
            409,
            f"{month_start(entry_date):%B %Y} is locked; post the correction in an open month.",
        )

    normalized: List[Tuple[uuid.UUID, Decimal, Decimal]] = []
    for account, debit, credit in lines:
        debit = money(debit)
        credit = money(credit)
        if debit < ZERO or credit < ZERO:
            raise CashbookError(400, "Amounts cannot be negative")
        if debit > ZERO and credit > ZERO:
            raise CashbookError(400, "A line must be on one side only")
        if debit == ZERO and credit == ZERO:
            continue
        normalized.append((_account_id(account), debit, credit))

    if len(normalized) < 2:
        raise CashbookError(400, "An entry needs at least two lines")
    total_debit = sum((item[1] for item in normalized), ZERO)
    total_credit = sum((item[2] for item in normalized), ZERO)
    if total_debit != total_credit:
        raise CashbookError(
            400, f"The entry does not balance: debits {total_debit}, credits {total_credit}"
        )

    entry = models.CashbookEntry(
        entry_date=entry_date,
        narration=narration[:255],
        reference=reference[:64] if reference else None,
        source=source,
        source_id=source_id,
        reverses_entry_id=reverses_entry_id,
        reversal_reason=reversal_reason,
        posted_by_user_id=actor_id,
        posted_at=datetime.utcnow(),
    )
    try:
        # A savepoint lets a concurrent duplicate (unique source/source_id)
        # be read back instead of poisoning the caller's transaction.
        with db.begin_nested():
            db.add(entry)
            db.flush()
    except IntegrityError:
        if source_id is None:
            raise
        existing = (
            db.query(models.CashbookEntry)
            .filter(
                models.CashbookEntry.source == source,
                models.CashbookEntry.source_id == source_id,
            )
            .first()
        )
        if existing is None:
            raise
        return existing

    for account_id, debit, credit in normalized:
        db.add(
            models.CashbookLine(
                entry_id=entry.id,
                account_id=account_id,
                debit=debit,
                credit=credit,
            )
        )
    db.flush()
    return entry


def reverse(
    db: Session,
    entry: models.CashbookEntry,
    *,
    reason: str,
    actor_id: Optional[uuid.UUID] = None,
    entry_date: Optional[date] = None,
    source: models.CashbookEntrySource = models.CashbookEntrySource.REVERSAL,
    source_id: Optional[uuid.UUID] = None,
) -> models.CashbookEntry:
    """Post the mirror image of ``entry`` so both stay in the history."""
    reason = (reason or "").strip()
    if not reason:
        raise CashbookError(400, "A reason is required to reverse an entry")
    existing = (
        db.query(models.CashbookEntry)
        .filter(models.CashbookEntry.reverses_entry_id == entry.id)
        .first()
    )
    if existing is not None:
        raise CashbookError(409, "This entry has already been reversed")

    mirrored = [
        (line.account_id, line.credit, line.debit) for line in entry.lines
    ]
    return post(
        db,
        entry_date=entry_date or date.today(),
        narration=f"Reversal: {entry.narration}",
        lines=mirrored,
        source=source,
        source_id=source_id,
        reference=entry.reference,
        actor_id=actor_id,
        reverses_entry_id=entry.id,
        reversal_reason=reason,
    )


def post_opening(
    db: Session,
    *,
    as_of: date,
    lines: Sequence[Tuple[Any, Decimal, Decimal]],
    actor_id: Optional[uuid.UUID] = None,
) -> models.CashbookEntry:
    """The one opening journal: assets and liabilities brought forward at
    go-live. It must be the first entry in the book."""
    if not module_enabled(db):
        raise CashbookError(403, "The Cashbook module is disabled by an administrator.")
    if opening_entry(db) is not None:
        raise CashbookError(409, "Opening balances have already been posted")
    later = db.query(models.CashbookEntry.id).first()
    if later is not None:
        raise CashbookError(
            409, "Opening balances must be the first entry; this book already has activity."
        )
    return post(
        db,
        entry_date=as_of,
        narration="Opening balances",
        lines=lines,
        source=models.CashbookEntrySource.OPENING,
        actor_id=actor_id,
    )


# ---------------------------------------------------------------------------
# Interest recognition
# ---------------------------------------------------------------------------

def loan_interest_for_payment(
    loan: models.Loan,
    amount: Decimal,
    *,
    repaid_before: Optional[Decimal] = None,
) -> Decimal:
    """The interest share of ``amount`` collected on ``loan``.

    ``at_source`` loans recognised everything at disbursement, so a
    repayment is pure principal. For the spread modes the share follows
    what has been collected; when the payment clears the loan the exact
    remainder is taken, which keeps cumulative rounding error from
    stranding a cent of interest.
    """
    amount = money(amount)
    if amount <= ZERO:
        return ZERO
    # NULL predates the interest modes feature and behaved as at-source.
    if loan is None or loan.interest_mode in (
        None,
        models.InterestDeductionMode.AT_SOURCE,
    ):
        return ZERO
    interest_amount = money(loan.interest_amount)
    total = money(loan.total_repayable)
    if interest_amount <= ZERO or total <= ZERO:
        return ZERO

    if repaid_before is None:
        repaid_before = money(loan.amount_repaid)
    else:
        repaid_before = money(repaid_before)
    if repaid_before < ZERO:
        repaid_before = ZERO

    if repaid_before + amount >= total:
        already = money(repaid_before * interest_amount / total)
        portion = interest_amount - already
    else:
        portion = money(amount * interest_amount / total)

    portion = min(max(portion, ZERO), interest_amount, amount)
    return money(portion)


# ---------------------------------------------------------------------------
# Automatic postings, one per money flow
# ---------------------------------------------------------------------------

def _entry_date(value: Optional[date]) -> date:
    return value or date.today()


def post_payroll_deduction(
    db: Session,
    deduction: models.PayrollDeduction,
    *,
    actor_id: Optional[uuid.UUID] = None,
    entry_date: Optional[date] = None,
) -> Optional[models.CashbookEntry]:
    """Payroll remitted the month's deductions: the bank receives the
    total, split into savings, loan principal, loan interest and amounts
    owed onward to other departments."""
    if not books_open(db):
        return None
    total = money(deduction.grand_total)
    if total <= ZERO:
        return None
    accounts = system_accounts(
        db,
        BANK,
        MEMBER_SAVINGS,
        LOAN_RECEIVABLE,
        INTEREST_INCOME,
        OTHER_DEDUCTIONS_PAYABLE,
    )

    contributions = ZERO
    other = ZERO
    loan_totals: Dict[uuid.UUID, Tuple[models.Loan, Decimal]] = {}
    for line in deduction.lines:
        amount = money(line.amount)
        if line.category == models.PayrollDeductionLineCategory.MONTHLY_CONTRIBUTION:
            contributions += amount
        elif line.category == models.PayrollDeductionLineCategory.OTHER:
            other += amount
        else:
            loan = line.loan
            if loan is None:
                raise CashbookError(409, f"Deduction line {line.id} has no loan to post against")
            held = loan_totals.get(loan.id)
            loan_totals[loan.id] = (loan, amount if held is None else held[1] + amount)

    principal = ZERO
    interest = ZERO
    for loan, amount in loan_totals.values():
        portion = loan_interest_for_payment(loan, amount)
        interest += portion
        principal += money(amount) - portion

    return post(
        db,
        entry_date=_entry_date(entry_date),
        narration=f"Payroll deductions {deduction.deduction_month:%B %Y}",
        reference=deduction.payroll_reference or f"{deduction.deduction_month:%Y-%m} payroll",
        source=models.CashbookEntrySource.PAYROLL_DEDUCTION,
        source_id=deduction.id,
        actor_id=actor_id,
        lines=[
            (accounts[BANK], total, ZERO),
            (accounts[MEMBER_SAVINGS], ZERO, contributions),
            (accounts[LOAN_RECEIVABLE], ZERO, principal),
            (accounts[INTEREST_INCOME], ZERO, interest),
            (accounts[OTHER_DEDUCTIONS_PAYABLE], ZERO, other),
        ],
    )


def reverse_payroll_deduction(
    db: Session,
    deduction: models.PayrollDeduction,
    *,
    reason: str,
    actor_id: Optional[uuid.UUID] = None,
) -> Optional[models.CashbookEntry]:
    """Voiding a confirmed deduction reverses its journal entry."""
    if not module_enabled(db):
        return None
    entry = (
        db.query(models.CashbookEntry)
        .options(joinedload(models.CashbookEntry.lines))
        .filter(
            models.CashbookEntry.source == models.CashbookEntrySource.PAYROLL_DEDUCTION,
            models.CashbookEntry.source_id == deduction.id,
        )
        .first()
    )
    if entry is None:
        return None
    return reverse(
        db,
        entry,
        reason=reason,
        actor_id=actor_id,
        source=models.CashbookEntrySource.PAYROLL_DEDUCTION_VOID,
        source_id=deduction.id,
    )


def post_loan_disbursement(
    db: Session,
    loan: models.Loan,
    *,
    offset_principal: Decimal = ZERO,
    offset_interest: Decimal = ZERO,
    actor_id: Optional[uuid.UUID] = None,
) -> Optional[models.CashbookEntry]:
    """A new loan leaves the cooperative: the receivable grows by the
    principal, the net payout leaves the bank, and any loan balance
    deducted from the payout settles those loans' principal and interest.

    ``offset_principal``/``offset_interest`` are computed by the caller
    before it closes the old loans out, using ``loan_interest_for_payment``.
    """
    if not books_open(db):
        return None
    accounts = system_accounts(db, BANK, LOAN_RECEIVABLE, INTEREST_INCOME)
    interest_at_source = (
        money(loan.interest_amount)
        if loan.interest_mode in (None, models.InterestDeductionMode.AT_SOURCE)
        else ZERO
    )
    return post(
        db,
        entry_date=loan.disbursement_date,
        narration=f"Loan disbursed: {loan.loan_type.name if loan.loan_type else 'loan'}",
        reference=f"loan-{loan.id}",
        source=models.CashbookEntrySource.LOAN_DISBURSEMENT,
        source_id=loan.id,
        actor_id=actor_id,
        lines=[
            (accounts[LOAN_RECEIVABLE], money(loan.principal), ZERO),
            (accounts[BANK], ZERO, money(loan.net_disbursed)),
            (accounts[LOAN_RECEIVABLE], ZERO, money(offset_principal)),
            (accounts[INTEREST_INCOME], ZERO, money(offset_interest)),
            (accounts[INTEREST_INCOME], ZERO, interest_at_source),
        ],
    )


def post_loan_repayment(
    db: Session,
    repayment: models.LoanRepayment,
    loan: models.Loan,
    *,
    repaid_before: Decimal,
    actor_id: Optional[uuid.UUID] = None,
    entry_date: Optional[date] = None,
) -> Optional[models.CashbookEntry]:
    if not books_open(db):
        return None
    amount = money(repayment.amount_claimed)
    if amount <= ZERO:
        return None
    accounts = system_accounts(db, BANK, LOAN_RECEIVABLE, INTEREST_INCOME)
    interest = loan_interest_for_payment(loan, amount, repaid_before=repaid_before)
    return post(
        db,
        entry_date=_entry_date(entry_date),
        narration="Loan repayment",
        reference=repayment.payment_reference,
        source=models.CashbookEntrySource.LOAN_REPAYMENT,
        source_id=repayment.id,
        actor_id=actor_id,
        lines=[
            (accounts[BANK], amount, ZERO),
            (accounts[LOAN_RECEIVABLE], ZERO, amount - interest),
            (accounts[INTEREST_INCOME], ZERO, interest),
        ],
    )


def _post_loan_fee(
    db: Session,
    *,
    source_id: uuid.UUID,
    amount: Decimal,
    reference: str,
    actor_id: Optional[uuid.UUID] = None,
    entry_date: Optional[date] = None,
) -> Optional[models.CashbookEntry]:
    amount = money(amount)
    if amount <= ZERO or not module_enabled(db):
        return None
    require_open_books(db)
    accounts = system_accounts(db, BANK, LOAN_FEE_INCOME)
    return post(
        db,
        entry_date=_entry_date(entry_date),
        narration="Loan fee received",
        reference=reference,
        source=models.CashbookEntrySource.LOAN_FEE,
        source_id=source_id,
        actor_id=actor_id,
        lines=[
            (accounts[BANK], amount, ZERO),
            (accounts[LOAN_FEE_INCOME], ZERO, amount),
        ],
    )


def post_loan_fee(
    db: Session,
    payment: models.LoanFeePayment,
    *,
    actor_id: Optional[uuid.UUID] = None,
    entry_date: Optional[date] = None,
) -> Optional[models.CashbookEntry]:
    return _post_loan_fee(
        db,
        source_id=payment.id,
        amount=payment.amount,
        reference=payment.payment_reference,
        actor_id=actor_id,
        entry_date=entry_date,
    )


def post_application_fee(
    db: Session,
    application: models.LoanApplication,
    *,
    actor_id: Optional[uuid.UUID] = None,
    entry_date: Optional[date] = None,
) -> Optional[models.CashbookEntry]:
    amount = money(application.form_fee_amount)
    if amount <= ZERO:
        return None
    require_open_books(db)
    return _post_loan_fee(
        db,
        source_id=application.id,
        amount=amount,
        reference=application.payment_reference,
        actor_id=actor_id,
        entry_date=entry_date,
    )


def post_settlement(
    db: Session,
    settlement: models.MemberSettlement,
    *,
    actor_id: Optional[uuid.UUID] = None,
) -> Optional[models.CashbookEntry]:
    """Savings leave the savings liability: the loan allocations settle
    principal and interest, and what remains becomes money owed to the
    member until the payout is marked paid."""
    if not books_open(db):
        return None
    balance = money(settlement.savings_balance)
    if balance <= ZERO:
        return None
    accounts = system_accounts(
        db, MEMBER_SAVINGS, LOAN_RECEIVABLE, INTEREST_INCOME, PAYOUT_PAYABLE
    )

    loan_ids = [allocation.loan_id for allocation in settlement.allocations]
    loans = {}
    if loan_ids:
        loans = {
            loan.id: loan
            for loan in db.query(models.Loan).filter(models.Loan.id.in_(loan_ids)).all()
        }

    principal = ZERO
    interest = ZERO
    for allocation in settlement.allocations:
        loan = loans.get(allocation.loan_id)
        if loan is None:
            raise CashbookError(409, f"Settlement allocation names missing loan {allocation.loan_id}")
        amount = money(allocation.amount)
        portion = loan_interest_for_payment(
            loan, amount, repaid_before=money(loan.amount_repaid) - amount
        )
        interest += portion
        principal += amount - portion

    return post(
        db,
        entry_date=settlement.settled_on,
        narration="Membership exit settlement",
        reference=f"settlement-{settlement.id}",
        source=models.CashbookEntrySource.SETTLEMENT,
        source_id=settlement.id,
        actor_id=actor_id,
        lines=[
            (accounts[MEMBER_SAVINGS], balance, ZERO),
            (accounts[LOAN_RECEIVABLE], ZERO, principal),
            (accounts[INTEREST_INCOME], ZERO, interest),
            (accounts[PAYOUT_PAYABLE], ZERO, money(settlement.payout_amount)),
        ],
    )


def post_settlement_payout(
    db: Session,
    settlement: models.MemberSettlement,
    *,
    actor_id: Optional[uuid.UUID] = None,
) -> Optional[models.CashbookEntry]:
    """The office hands the exit payout over, from cash or the bank."""
    if not books_open(db):
        return None
    amount = money(settlement.payout_amount)
    if amount <= ZERO:
        return None
    if settlement.paid_from is None:
        raise CashbookError(
            400, "Record whether the payout was paid from cash or the bank before posting it"
        )
    paid_key = CASH if settlement.paid_from == models.SettlementPaymentMethod.CASH else BANK
    accounts = system_accounts(db, PAYOUT_PAYABLE, paid_key)
    return post(
        db,
        entry_date=settlement.paid_on or date.today(),
        narration="Exit payout paid",
        reference=settlement.paid_reference,
        source=models.CashbookEntrySource.SETTLEMENT_PAYOUT,
        source_id=settlement.id,
        actor_id=actor_id,
        lines=[
            (accounts[PAYOUT_PAYABLE], amount, ZERO),
            (accounts[paid_key], ZERO, amount),
        ],
    )


# ---------------------------------------------------------------------------
# Reports
# ---------------------------------------------------------------------------

class AccountTotal(NamedTuple):
    account: models.CashbookAccount
    debit: Decimal
    credit: Decimal


class TrialBalanceRow(NamedTuple):
    account: models.CashbookAccount
    debit: Decimal
    credit: Decimal


class TrialBalance(NamedTuple):
    rows: List[TrialBalanceRow]
    total_debit: Decimal
    total_credit: Decimal


class MovementRow(NamedTuple):
    account: models.CashbookAccount
    amount: Decimal


class IncomeStatement(NamedTuple):
    income: List[MovementRow]
    expenses: List[MovementRow]
    total_income: Decimal
    total_expenses: Decimal
    surplus: Decimal


class BalanceSheet(NamedTuple):
    assets: List[MovementRow]
    liabilities: List[MovementRow]
    equity: List[MovementRow]
    surplus: Decimal
    total_assets: Decimal
    total_liabilities: Decimal
    total_equity: Decimal


class LedgerRow(NamedTuple):
    entry_date: date
    narration: str
    reference: Optional[str]
    debit: Decimal
    credit: Decimal
    balance: Decimal


class AccountLedger(NamedTuple):
    account: models.CashbookAccount
    opening_balance: Decimal
    rows: List[LedgerRow]
    closing_balance: Decimal


class RegisterRow(NamedTuple):
    entry_date: date
    narration: str
    reference: Optional[str]
    account: models.CashbookAccount
    amount: Decimal


def _totals_by_account(
    db: Session,
    *,
    start: Optional[date] = None,
    end: Optional[date] = None,
    exclude_sources: Sequence[models.CashbookEntrySource] = (),
) -> Dict[uuid.UUID, AccountTotal]:
    query = (
        db.query(
            models.CashbookLine.account_id,
            func.coalesce(func.sum(models.CashbookLine.debit), 0),
            func.coalesce(func.sum(models.CashbookLine.credit), 0),
        )
        .join(models.CashbookEntry, models.CashbookEntry.id == models.CashbookLine.entry_id)
        .group_by(models.CashbookLine.account_id)
    )
    if start is not None:
        query = query.filter(models.CashbookEntry.entry_date >= start)
    if end is not None:
        query = query.filter(models.CashbookEntry.entry_date <= end)
    if exclude_sources:
        query = query.filter(models.CashbookEntry.source.notin_(exclude_sources))

    accounts = {
        account.id: account for account in db.query(models.CashbookAccount).all()
    }
    totals: Dict[uuid.UUID, AccountTotal] = {}
    for account_id, debit, credit in query.all():
        account = accounts.get(account_id)
        if account is None:
            continue
        totals[account_id] = AccountTotal(account, money(debit), money(credit))
    return totals


def _debit_normal(account: models.CashbookAccount) -> bool:
    return account.kind in (
        models.CashbookAccountKind.ASSET,
        models.CashbookAccountKind.EXPENSE,
    )


def account_balances(db: Session, *, as_of: Optional[date] = None) -> List[AccountTotal]:
    totals = _totals_by_account(db, end=as_of)
    return sorted(totals.values(), key=lambda row: row.account.code)


def trial_balance(db: Session, *, as_of: Optional[date] = None) -> TrialBalance:
    """Every account's net balance on its side of the trial balance. The
    totals must agree; nothing else in the cashbook is trusted if they
    do not."""
    rows: List[TrialBalanceRow] = []
    total_debit = ZERO
    total_credit = ZERO
    for item in account_balances(db, as_of=as_of):
        net = item.debit - item.credit
        if net > ZERO:
            rows.append(TrialBalanceRow(item.account, net, ZERO))
            total_debit += net
        elif net < ZERO:
            rows.append(TrialBalanceRow(item.account, ZERO, -net))
            total_credit += -net
    return TrialBalance(rows=rows, total_debit=total_debit, total_credit=total_credit)


def income_statement(
    db: Session, *, start: Optional[date] = None, end: Optional[date] = None
) -> IncomeStatement:
    # Closing entries move the year's income and expenditure into retained
    # earnings. They are not income or expense themselves, so the report
    # excludes them -- a closed year still shows what it earned and spent.
    totals = _totals_by_account(
        db,
        start=start,
        end=end,
        exclude_sources=(models.CashbookEntrySource.YEAR_CLOSE,),
    )
    income: List[MovementRow] = []
    expenses: List[MovementRow] = []
    total_income = ZERO
    total_expenses = ZERO
    for item in sorted(totals.values(), key=lambda row: row.account.code):
        if item.account.kind == models.CashbookAccountKind.INCOME:
            amount = item.credit - item.debit
            if amount != ZERO:
                income.append(MovementRow(item.account, amount))
                total_income += amount
        elif item.account.kind == models.CashbookAccountKind.EXPENSE:
            amount = item.debit - item.credit
            if amount != ZERO:
                expenses.append(MovementRow(item.account, amount))
                total_expenses += amount
    return IncomeStatement(
        income=income,
        expenses=expenses,
        total_income=total_income,
        total_expenses=total_expenses,
        surplus=total_income - total_expenses,
    )


def balance_sheet(db: Session, *, as_of: Optional[date] = None) -> BalanceSheet:
    """Assets against liabilities and equity, with the unclosed surplus
    (income less expense since the last closing entry) in equity. When
    they do not agree, a posting broke the double entry -- the figures
    are still returned so the report can show the discrepancy."""
    totals = _totals_by_account(db, end=as_of)
    assets: List[MovementRow] = []
    liabilities: List[MovementRow] = []
    equity: List[MovementRow] = []
    total_assets = ZERO
    total_liabilities = ZERO
    total_equity = ZERO
    surplus = ZERO

    for item in sorted(totals.values(), key=lambda row: row.account.code):
        if item.account.kind == models.CashbookAccountKind.ASSET:
            amount = item.debit - item.credit
            if amount != ZERO:
                assets.append(MovementRow(item.account, amount))
                total_assets += amount
        elif item.account.kind == models.CashbookAccountKind.LIABILITY:
            amount = item.credit - item.debit
            if amount != ZERO:
                liabilities.append(MovementRow(item.account, amount))
                total_liabilities += amount
        elif item.account.kind == models.CashbookAccountKind.EQUITY:
            amount = item.credit - item.debit
            if amount != ZERO:
                equity.append(MovementRow(item.account, amount))
                total_equity += amount
        elif item.account.kind == models.CashbookAccountKind.INCOME:
            surplus += item.credit - item.debit
        elif item.account.kind == models.CashbookAccountKind.EXPENSE:
            surplus -= item.debit - item.credit

    return BalanceSheet(
        assets=assets,
        liabilities=liabilities,
        equity=equity,
        surplus=surplus,
        total_assets=total_assets,
        total_liabilities=total_liabilities,
        total_equity=total_equity + surplus,
    )


def account_ledger(
    db: Session,
    account: models.CashbookAccount,
    *,
    start: Optional[date] = None,
    end: Optional[date] = None,
) -> AccountLedger:
    def on_normal_side(net: Decimal) -> Decimal:
        return net if _debit_normal(account) else -net

    # No start date means the ledger shows the account from its first
    # entry, so there is nothing before the first row. Counting every
    # line here as well would double the balance.
    opening_balance = ZERO
    if start is not None:
        opening_debit, opening_credit = (
            db.query(
                func.coalesce(func.sum(models.CashbookLine.debit), 0),
                func.coalesce(func.sum(models.CashbookLine.credit), 0),
            )
            .join(models.CashbookEntry, models.CashbookEntry.id == models.CashbookLine.entry_id)
            .filter(
                models.CashbookLine.account_id == account.id,
                models.CashbookEntry.entry_date < start,
            )
            .one()
        )
        opening_balance = on_normal_side(money(opening_debit) - money(opening_credit))

    query = (
        db.query(
            models.CashbookEntry.entry_date,
            models.CashbookEntry.narration,
            models.CashbookEntry.reference,
            models.CashbookLine.debit,
            models.CashbookLine.credit,
        )
        .join(models.CashbookEntry, models.CashbookEntry.id == models.CashbookLine.entry_id)
        .filter(models.CashbookLine.account_id == account.id)
        .order_by(
            models.CashbookEntry.entry_date.asc(),
            models.CashbookEntry.created_at.asc(),
            models.CashbookLine.created_at.asc(),
        )
    )
    if start is not None:
        query = query.filter(models.CashbookEntry.entry_date >= start)
    if end is not None:
        query = query.filter(models.CashbookEntry.entry_date <= end)

    running = opening_balance
    debit_normal = _debit_normal(account)
    rows: List[LedgerRow] = []
    for entry_date, narration, reference, debit, credit in query.all():
        debit = money(debit)
        credit = money(credit)
        # `running` is already on the account's normal side, so each
        # movement is added on that side rather than re-normalised.
        running += debit - credit if debit_normal else credit - debit
        rows.append(LedgerRow(entry_date, narration, reference, debit, credit, running))

    return AccountLedger(
        account=account,
        opening_balance=opening_balance,
        rows=rows,
        closing_balance=running,
    )


def cash_register(
    db: Session,
    *,
    start: Optional[date] = None,
    end: Optional[date] = None,
) -> List[RegisterRow]:
    """Every movement through cash on hand and the bank, in date order.
    Positive is money in; negative is money out."""
    query = (
        db.query(models.CashbookEntry, models.CashbookLine, models.CashbookAccount)
        .join(models.CashbookLine, models.CashbookLine.entry_id == models.CashbookEntry.id)
        .join(models.CashbookAccount, models.CashbookAccount.id == models.CashbookLine.account_id)
        .filter(models.CashbookAccount.system_key.in_([CASH, BANK]))
        .order_by(
            models.CashbookEntry.entry_date.asc(),
            models.CashbookEntry.created_at.asc(),
            models.CashbookLine.created_at.asc(),
        )
    )
    if start is not None:
        query = query.filter(models.CashbookEntry.entry_date >= start)
    if end is not None:
        query = query.filter(models.CashbookEntry.entry_date <= end)

    rows: List[RegisterRow] = []
    for entry, line, account in query.all():
        rows.append(
            RegisterRow(
                entry_date=entry.entry_date,
                narration=entry.narration,
                reference=entry.reference,
                account=account,
                amount=money(line.debit) - money(line.credit),
            )
        )
    return rows
