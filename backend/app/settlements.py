"""Settling a departing member's savings against their loans.

Recording a membership exit (POST /members/{id}/withdraw) only marks the
status and the exit date -- it never moves money. Settlement is the
deliberate second step, run once the member's final payroll month is
confirmed:

  1. their savings (the ledger balance) are applied to active loans, oldest
     loan first, and a loan that is repaid in full is completed;
  2. whatever is left becomes a payout the office owes the member;
  3. marking that payout paid records the handover (date + reference).

The member-level books are posted here: the savings ledger is debited in
full at settlement. The cooperative-level cash movement is NOT posted --
the cashbook does not exist yet -- so a pending payout is a recorded claim
against the office, not a cashbook entry. When the cashbook lands it posts
the cash at mark-paid.

Figures on the settlement are snapshots. A later payroll correction cannot
rewrite what the office settled with the member.
"""
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional, Tuple

from sqlalchemy.orm import Session, joinedload

from . import models, notification_service, savings

ZERO = Decimal("0")

LIVE_DEDUCTION_STATUSES = (
    models.PayrollDeductionStatus.DRAFT,
    models.PayrollDeductionStatus.SUBMITTED,
)


class SettlementError(Exception):
    """A guard the caller must turn into an HTTP error. The status code
    travels with it so the message and the code stay in one place."""

    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def lock_member(db: Session, member_id: uuid.UUID) -> Optional[models.Member]:
    """Serialize two settlement attempts on the same member. The unique
    constraint on member_settlements.member_id is the hard backstop; the
    lock turns the loser into a clean 409 instead of an integrity error."""
    return (
        db.query(models.Member)
        .filter(models.Member.id == member_id)
        .with_for_update(of=models.Member)
        .first()
    )


def active_loans(db: Session, member_id: uuid.UUID) -> List[models.Loan]:
    """Loans still owed on, oldest first -- settlement order and the
    preview's outstanding total both come from this one list."""
    return (
        db.query(models.Loan)
        .options(joinedload(models.Loan.loan_type))
        .filter(
            models.Loan.member_id == member_id,
            models.Loan.status == models.LoanStatus.ACTIVE,
            models.Loan.total_repayable > models.Loan.amount_repaid,
        )
        .order_by(models.Loan.disbursement_date.asc(), models.Loan.id.asc())
        .all()
    )


def outstanding_total(loans: List[models.Loan]) -> Decimal:
    return sum((loan.total_repayable - loan.amount_repaid for loan in loans), ZERO)


def for_member(db: Session, member_id: uuid.UUID) -> Optional[models.MemberSettlement]:
    return (
        db.query(models.MemberSettlement)
        .options(
            joinedload(models.MemberSettlement.allocations).joinedload(
                models.SettlementAllocation.loan
            ).joinedload(models.Loan.loan_type)
        )
        .filter(models.MemberSettlement.member_id == member_id)
        .first()
    )


def settle(
    db: Session,
    member: models.Member,
    *,
    actor: models.User,
    settled_on: Optional[date] = None,
    note: Optional[str] = None,
) -> models.MemberSettlement:
    """Apply the member's savings to their loans and record the payout
    claim. Adds rows only -- the caller commits, so the settlement, the
    loan updates and the ledger debits land together."""
    if member.membership_exit_date is None:
        raise SettlementError(
            409, "Record the membership exit before settling savings."
        )
    existing = (
        db.query(models.MemberSettlement.id)
        .filter(models.MemberSettlement.member_id == member.id)
        .first()
    )
    if existing is not None:
        raise SettlementError(409, "This member's exit has already been settled.")

    live = (
        db.query(models.PayrollDeduction.id)
        .filter(
            models.PayrollDeduction.member_id == member.id,
            models.PayrollDeduction.status.in_(LIVE_DEDUCTION_STATUSES),
        )
        .first()
    )
    if live is not None:
        raise SettlementError(
            409,
            "This member has payroll deductions still in progress. Finish or void them before settling.",
        )

    settled_on = settled_on or date.today()
    if settled_on > date.today():
        raise SettlementError(400, "The settlement date can't be in the future")

    balance = savings.balance(db, member.id)
    if balance < ZERO:
        raise SettlementError(
            409, "The member's savings ledger is negative; correct it before settling."
        )

    # Lock every loan being settled so a concurrent repayment verification
    # cannot credit the same balance while we read it.
    loans = [
        loan
        for loan in (
            db.query(models.Loan)
            .filter(
                models.Loan.member_id == member.id,
                models.Loan.status == models.LoanStatus.ACTIVE,
                models.Loan.total_repayable > models.Loan.amount_repaid,
            )
            .order_by(models.Loan.disbursement_date.asc(), models.Loan.id.asc())
            .with_for_update(of=models.Loan)
            .all()
        )
    ]
    owed = outstanding_total(loans)

    if balance <= ZERO and owed <= ZERO:
        raise SettlementError(
            400, "There is nothing to settle: no savings and no loan balance."
        )

    remaining = balance
    allocations: List[models.SettlementAllocation] = []
    for loan in loans:
        if remaining <= ZERO:
            break
        applied = min(remaining, loan.total_repayable - loan.amount_repaid)
        if applied <= ZERO:
            continue
        loan.amount_repaid = loan.amount_repaid + applied
        if loan.amount_repaid >= loan.total_repayable:
            loan.status = models.LoanStatus.COMPLETED
        remaining -= applied
        allocations.append(models.SettlementAllocation(loan_id=loan.id, amount=applied))

    offset_total = balance - remaining
    payout_amount = remaining

    settlement = models.MemberSettlement(
        member_id=member.id,
        settled_on=settled_on,
        settled_by_user_id=actor.id,
        savings_balance=balance,
        offset_total=offset_total,
        payout_amount=payout_amount,
        note=note,
    )
    if payout_amount <= ZERO:
        # Nothing is owed, so there is no handover to wait for.
        settlement.payout_status = models.SettlementPayoutStatus.PAID
        settlement.paid_on = settled_on
        settlement.paid_at = datetime.utcnow()
    settlement.allocations = allocations

    db.add(settlement)
    db.flush()

    savings.post_settlement_entries(db, settlement, actor_id=actor.id)

    if payout_amount > ZERO:
        body = (
            f"Savings of {balance} were applied at your exit: {offset_total} toward your "
            f"loans and {payout_amount} is due to be paid out to you."
        )
    else:
        body = f"Savings of {balance} were applied to your loans at your exit."
    notification_service.notify_member(
        db,
        member,
        category=models.NotificationCategory.ACCOUNT,
        title="Membership exit settled",
        body=body,
        link_path="/dashboard",
    )
    return settlement


def mark_paid(
    db: Session,
    settlement: models.MemberSettlement,
    *,
    member: models.Member,
    paid_on: Optional[date] = None,
    reference: str,
) -> models.MemberSettlement:
    """Record that the office handed the payout over. The ledger is not
    touched -- the member's savings were already spent at settlement;
    this is the evidence of the handover."""
    if settlement.payout_status == models.SettlementPayoutStatus.PAID:
        raise SettlementError(409, "This settlement's payout is already recorded as paid.")
    if settlement.payout_amount <= ZERO:
        raise SettlementError(409, "There is no payout to mark paid.")

    paid_on = paid_on or date.today()
    if paid_on > date.today():
        raise SettlementError(400, "The payment date can't be in the future")
    if paid_on < settlement.settled_on:
        raise SettlementError(400, "The payment date can't be before the settlement date")

    settlement.payout_status = models.SettlementPayoutStatus.PAID
    settlement.paid_on = paid_on
    settlement.paid_at = datetime.utcnow()
    settlement.paid_reference = reference

    notification_service.notify_member(
        db,
        member,
        category=models.NotificationCategory.ACCOUNT,
        title="Exit payout paid",
        body=f"Your exit payout of {settlement.payout_amount} has been paid. Reference: {reference}.",
        link_path="/dashboard",
    )
    return settlement
