"""The member savings ledger.

Savings is money the cooperative holds for a member -- a liability, not
income -- so it lives in its own append-only subledger instead of being
derived from a sign on some other list. Every row is one thing that
happened: payroll posted a contribution, a voided payroll month was
reversed, savings were applied to a loan on exit, or the remaining balance
was paid out. The balance is the sum of those rows and nothing is ever
edited.

The cashbook (when it lands) posts the cooperative-level side of each
movement; this ledger is the member-level side.
"""
import uuid
from decimal import Decimal
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from . import models

ZERO = Decimal("0")


def balance(db: Session, member_id: uuid.UUID) -> Decimal:
    """What the cooperative currently holds for one member."""
    rows = (
        db.query(
            models.SavingsEntry.entry_type,
            func.coalesce(func.sum(models.SavingsEntry.amount), 0),
        )
        .filter(models.SavingsEntry.member_id == member_id)
        .group_by(models.SavingsEntry.entry_type)
        .all()
    )
    credits = ZERO
    debits = ZERO
    for entry_type, total in rows:
        amount = Decimal(total or 0)
        if entry_type == models.SavingsEntryType.CONTRIBUTION:
            credits += amount
        else:
            debits += amount
    return credits - debits


def post_contribution(
    db: Session,
    deduction: models.PayrollDeduction,
    line: models.PayrollDeductionLine,
    *,
    actor_id: Optional[uuid.UUID],
) -> models.SavingsEntry:
    """Credit a confirmed contribution line. The unique (line, kind) index
    makes a double confirmation fail instead of silently doubling savings."""
    entry = models.SavingsEntry(
        member_id=deduction.member_id,
        entry_type=models.SavingsEntryType.CONTRIBUTION,
        amount=line.amount,
        deduction_line_id=line.id,
        posted_by_user_id=actor_id,
        note=f"{deduction.deduction_month:%Y-%m} payroll contribution",
    )
    db.add(entry)
    return entry


def reverse_contribution(
    db: Session,
    deduction: models.PayrollDeduction,
    line: models.PayrollDeductionLine,
    *,
    actor_id: Optional[uuid.UUID],
    note: str,
) -> models.SavingsEntry:
    """Undo a contribution with a counter-entry, never by deleting the
    original -- the ledger must still show the money was once held."""
    entry = models.SavingsEntry(
        member_id=deduction.member_id,
        entry_type=models.SavingsEntryType.CONTRIBUTION_REVERSAL,
        amount=line.amount,
        deduction_line_id=line.id,
        posted_by_user_id=actor_id,
        note=note,
    )
    db.add(entry)
    return entry


def reverse_for_deduction(
    db: Session,
    deduction: models.PayrollDeduction,
    *,
    actor_id: Optional[uuid.UUID],
    note: str,
) -> None:
    """Reverse every contribution this deduction posted, exactly once.

    Read from the ledger rather than from the lines: a confirmed record
    created before the ledger existed (or a fixture that touched the table
    directly) may have no entries, and reversing those would invent a
    debit. Already-reversed lines are skipped so a repeated call is safe.
    """
    line_ids = [
        line.id
        for line in deduction.lines
        if line.category == models.PayrollDeductionLineCategory.MONTHLY_CONTRIBUTION
    ]
    if not line_ids:
        return
    entries = (
        db.query(models.SavingsEntry)
        .filter(models.SavingsEntry.deduction_line_id.in_(line_ids))
        .all()
    )
    posted = {
        entry.deduction_line_id
        for entry in entries
        if entry.entry_type == models.SavingsEntryType.CONTRIBUTION
    }
    already_reversed = {
        entry.deduction_line_id
        for entry in entries
        if entry.entry_type == models.SavingsEntryType.CONTRIBUTION_REVERSAL
    }
    for line in deduction.lines:
        if line.id in posted and line.id not in already_reversed:
            reverse_contribution(db, deduction, line, actor_id=actor_id, note=note)


def post_settlement_entries(
    db: Session,
    settlement: models.MemberSettlement,
    *,
    actor_id: Optional[uuid.UUID],
) -> None:
    """Debit the whole balance at settlement: the loan offset and the
    amount paid out. Marking the payout paid later does not touch the
    ledger -- the member's savings are already spent."""
    if settlement.offset_total > ZERO:
        db.add(
            models.SavingsEntry(
                member_id=settlement.member_id,
                entry_type=models.SavingsEntryType.EXIT_OFFSET,
                amount=settlement.offset_total,
                settlement_id=settlement.id,
                posted_by_user_id=actor_id,
                note="Applied to active loans on exit",
            )
        )
    if settlement.payout_amount > ZERO:
        db.add(
            models.SavingsEntry(
                member_id=settlement.member_id,
                entry_type=models.SavingsEntryType.EXIT_PAYOUT,
                amount=settlement.payout_amount,
                settlement_id=settlement.id,
                posted_by_user_id=actor_id,
                note="Balance paid out on exit",
            )
        )
