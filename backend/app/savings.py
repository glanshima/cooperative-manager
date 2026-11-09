"""A member's savings balance -- their accumulated monthly contributions.

There is no separate savings ledger (see PayrollDeductionLine's note in
models.py), so the contribution lines payroll actually remitted ARE the
balance. Only `confirmed` deductions count: draft and submitted records
haven't reached the cooperative yet, not_deducted ones were skipped by
payroll, and voided ones were reversed.
"""
import uuid
from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.orm import Session

from . import models


def contributions_balance(db: Session, member_id: uuid.UUID) -> Decimal:
    total = (
        db.query(func.coalesce(func.sum(models.PayrollDeductionLine.amount), 0))
        .join(
            models.PayrollDeduction,
            models.PayrollDeduction.id == models.PayrollDeductionLine.deduction_id,
        )
        .filter(
            models.PayrollDeduction.member_id == member_id,
            models.PayrollDeduction.status == models.PayrollDeductionStatus.CONFIRMED,
            models.PayrollDeductionLine.category
            == models.PayrollDeductionLineCategory.MONTHLY_CONTRIBUTION,
        )
        .scalar()
    )
    return Decimal(total or 0)
