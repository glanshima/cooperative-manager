"""What each member is expected to pay through payroll for a given month.

The instalment is agreed when a loan is disbursed and the contribution is
agreed on the member record, so the ledger should pre-fill those figures
rather than ask an officer to retype them every month. This module is the
single source of that arithmetic: the worklist shows it and the draft
endpoints stamp it onto each line as `expected_amount`.

Rules (all agreed with the cooperative):

  - The contribution comes from the member's stored amount, priced for the
    month being entered (see contributions.amount_for_month), so a change
    approved this month never reprices a month already being worked on.
  - A loan's first instalment falls due the month AFTER disbursement.
  - A loan line is the instalment capped at the remaining balance, less
    anything the member already paid for THAT month by bank transfer and
    had verified -- otherwise they would pay the same instalment twice.
  - Arrears are reported, not silently accumulated: only the current
    month is pre-filled, with the shortfall and the number of months it
    covers shown alongside so the officer can decide.
  - Verified repayments with no recorded month cannot be attributed, so
    they are surfaced as a warning instead of being netted off a guess.
"""
import uuid
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Dict, List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from . import contributions, models

ZERO = Decimal("0.00")

DUE_CONTRIBUTION = "contribution"
DUE_CONTRIBUTION_AMOUNT_MISSING = "contribution_amount_missing"
DUE_LOAN_INSTALMENT = "loan_instalment"


def months_between(first: date, last: date) -> int:
    """Inclusive count of payroll months from first to last (0 if last is
    earlier)."""
    count = (last.year - first.year) * 12 + (last.month - first.month) + 1
    return max(count, 0)


@dataclass
class ExpectedLine:
    category: models.PayrollDeductionLineCategory
    amount: Decimal
    loan_id: Optional[uuid.UUID] = None
    loan_type_name: Optional[str] = None
    arrears: Decimal = ZERO
    months_behind: int = 0


@dataclass
class MemberExpectation:
    member_id: uuid.UUID
    member_name: str
    member_psn: str
    member_status: models.MemberStatus
    membership_exit_date: Optional[date]
    contribution_amount: Optional[Decimal]
    lines: List[ExpectedLine] = field(default_factory=list)
    due_reasons: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    @property
    def total(self) -> Decimal:
        return sum((line.amount for line in self.lines), ZERO)

    @property
    def is_due(self) -> bool:
        return bool(self.due_reasons)

    def amount_for(self, line: models.PayrollDeductionLine) -> Optional[Decimal]:
        """The expectation behind an entered line, or None when the officer
        typed a figure nothing on file predicts ('other' lines, or a loan
        that no longer expects an instalment this month)."""
        if line.category == models.PayrollDeductionLineCategory.MONTHLY_CONTRIBUTION:
            return self.contribution_amount
        if line.category == models.PayrollDeductionLineCategory.LOAN_REPAYMENT:
            for expected in self.lines:
                if expected.loan_id == line.loan_id:
                    return expected.amount
        return None

    def is_override(self, line: models.PayrollDeductionLine) -> bool:
        """True when the entered figure is not what the server predicted --
        either a different amount, or an amount nothing on file predicts at
        all (an 'other' line, or a loan already covered this month).

        Recording the expected figure is clerical; choosing a different one
        is a discretionary decision about a member's money, which is what
        the conflict-of-interest guard reserves to an unconflicted officer.
        """
        expected = self.amount_for(line)
        return expected is None or line.amount != expected

    def apply_to(self, lines: List[models.PayrollDeductionLine]) -> None:
        """Stamps the expectation onto entered lines. Never reads an
        expected amount from the client, so a difference between amount
        and expected_amount always means a deliberate override."""
        for line in lines:
            line.expected_amount = self.amount_for(line)


def _loans_owing(db: Session, member_ids: List[uuid.UUID]) -> List[models.Loan]:
    """Every loan that could still expect an instalment, oldest first. A
    settled or closed loan can never produce a line, so SQL drops it here
    rather than letting each one be priced and discarded."""
    if not member_ids:
        return []
    return (
        db.query(models.Loan)
        .options(joinedload(models.Loan.loan_type))
        .filter(
            models.Loan.member_id.in_(member_ids),
            models.Loan.status == models.LoanStatus.ACTIVE,
            models.Loan.total_repayable > models.Loan.amount_repaid,
        )
        .order_by(models.Loan.member_id, models.Loan.disbursement_date.asc())
        .all()
    )


def _verified_paid_by_loan(
    db: Session, loan_ids: List[uuid.UUID], month: date
) -> Dict[uuid.UUID, Decimal]:
    if not loan_ids:
        return {}
    rows = (
        db.query(models.LoanRepayment.loan_id, models.LoanRepayment.amount_claimed)
        .filter(
            models.LoanRepayment.loan_id.in_(loan_ids),
            models.LoanRepayment.payment_month == month,
            models.LoanRepayment.status == models.RepaymentVerificationStatus.VERIFIED,
        )
        .all()
    )
    totals: Dict[uuid.UUID, Decimal] = {}
    for loan_id, amount in rows:
        totals[loan_id] = totals.get(loan_id, ZERO) + amount
    return totals


def _unattributed_by_loan(db: Session, loan_ids: List[uuid.UUID]) -> Dict[uuid.UUID, int]:
    if not loan_ids:
        return {}
    rows = (
        db.query(models.LoanRepayment.loan_id, func.count(models.LoanRepayment.id))
        .filter(
            models.LoanRepayment.loan_id.in_(loan_ids),
            models.LoanRepayment.payment_month.is_(None),
            models.LoanRepayment.status == models.RepaymentVerificationStatus.VERIFIED,
        )
        .group_by(models.LoanRepayment.loan_id)
        .all()
    )
    return {loan_id: count for loan_id, count in rows}


def _loan_expectation(
    loan: models.Loan, month: date, paid_this_month: Decimal
) -> Optional[ExpectedLine]:
    remaining = loan.total_repayable - loan.amount_repaid

    first_due = contributions.next_month_start(loan.disbursement_date)
    due_months = months_between(first_due, month)
    if due_months == 0:
        return None

    instalment = min(loan.monthly_installment, remaining)
    amount = max(instalment - paid_this_month, ZERO)

    # Arrears are measured against what the schedule should have collected
    # by this month, not against the pre-filled line: a member who paid
    # this month's instalment by bank can still be behind on earlier ones.
    scheduled = min(loan.monthly_installment * due_months, loan.total_repayable)
    arrears = max(scheduled - loan.amount_repaid - paid_this_month, ZERO)
    months_behind = 0
    if arrears > ZERO and loan.monthly_installment > ZERO:
        months_behind = int(arrears // loan.monthly_installment)
        if arrears % loan.monthly_installment:
            months_behind += 1

    return ExpectedLine(
        category=models.PayrollDeductionLineCategory.LOAN_REPAYMENT,
        amount=amount,
        loan_id=loan.id,
        loan_type_name=loan.loan_type.name if loan.loan_type else None,
        arrears=arrears,
        months_behind=months_behind,
    )


def _price_member(
    db: Session,
    member: models.Member,
    month: date,
    loans: List[models.Loan],
    paid_by_loan: Dict[uuid.UUID, Decimal],
    unattributed_by_loan: Dict[uuid.UUID, int],
) -> MemberExpectation:
    """The pricing itself, with every lookup the member's loans need already
    in hand. `month` must already be normalized to the first of the month."""
    expectation = MemberExpectation(
        member_id=member.id,
        member_name=member.name,
        member_psn=member.psn,
        member_status=member.status,
        membership_exit_date=member.membership_exit_date,
        contribution_amount=contributions.amount_for_month(db, member, month),
    )

    if member.status == models.MemberStatus.FINANCIAL:
        if expectation.contribution_amount is None:
            expectation.due_reasons.append(DUE_CONTRIBUTION_AMOUNT_MISSING)
            expectation.warnings.append(
                "No monthly contribution on file for this month — record the agreed amount on the member first."
            )
        elif expectation.contribution_amount > ZERO:
            expectation.due_reasons.append(DUE_CONTRIBUTION)
            expectation.lines.append(
                ExpectedLine(
                    category=models.PayrollDeductionLineCategory.MONTHLY_CONTRIBUTION,
                    amount=expectation.contribution_amount,
                )
            )

    for loan in loans:
        line = _loan_expectation(loan, month, paid_by_loan.get(loan.id, ZERO))
        if line is None:
            continue
        unattributed = unattributed_by_loan.get(loan.id, 0)
        if unattributed:
            expectation.warnings.append(
                f"{line.loan_type_name or 'Loan'}: {unattributed} verified repayment(s) have no "
                "recorded payment month, so they are not netted off this month's instalment."
            )
        # A loan whose instalment is already covered still belongs in the
        # picture (arrears, warnings), but it is not a reason to enter a
        # deduction for this member.
        if line.amount > ZERO:
            if DUE_LOAN_INSTALMENT not in expectation.due_reasons:
                expectation.due_reasons.append(DUE_LOAN_INSTALMENT)
        expectation.lines.append(line)

    return expectation


def for_member(db: Session, member: models.Member, month: date) -> MemberExpectation:
    month = contributions.month_start(month)
    loans = _loans_owing(db, [member.id])
    loan_ids = [loan.id for loan in loans]
    return _price_member(
        db,
        member,
        month,
        loans,
        _verified_paid_by_loan(db, loan_ids, month),
        _unattributed_by_loan(db, loan_ids),
    )


def for_month(db: Session, month: date) -> List[MemberExpectation]:
    """Every member's expectation for a payroll month, ordered by name.

    The whole month is priced at once because the queue's totals are
    month-wide: which members are due, and how much is still outstanding,
    cannot come from a page. Batching is what makes that affordable -- the
    loan and repayment lookups run once across every member instead of once
    per member, so pricing 190 members costs a handful of queries rather
    than a thousand."""
    month = contributions.month_start(month)
    members = db.query(models.Member).order_by(models.Member.name).all()
    loans = _loans_owing(db, [member.id for member in members])
    loan_ids = [loan.id for loan in loans]
    paid_by_loan = _verified_paid_by_loan(db, loan_ids, month)
    unattributed_by_loan = _unattributed_by_loan(db, loan_ids)

    by_member: Dict[uuid.UUID, List[models.Loan]] = {}
    for loan in loans:
        by_member.setdefault(loan.member_id, []).append(loan)

    return [
        _price_member(
            db,
            member,
            month,
            by_member.get(member.id, []),
            paid_by_loan,
            unattributed_by_loan,
        )
        for member in members
    ]


def has_override(lines: List[models.PayrollDeductionLine]) -> bool:
    """Whether an already-entered record deviates from what was expected
    when it was drafted. Used at submission, where the stamped expectation
    -- not a freshly computed one -- is what the officer agreed to."""
    return any(line.expected_amount is None or line.amount != line.expected_amount for line in lines)