"""Rules that hold for every path that can activate a loan."""
import uuid
from typing import Iterable

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from . import models

ACTIVE_LOAN_TYPE_INDEX = "uq_loans_member_loan_type_active"


def assert_no_other_active_loan_of_type(
    db: Session,
    member_id: uuid.UUID,
    loan_type_id: uuid.UUID,
    *,
    exclude_loan_ids: Iterable[uuid.UUID] = (),
) -> None:
    """A member may hold at most one ACTIVE loan per loan type at a time.

    The API check produces a clear 409 for normal use; the partial unique
    index uq_loans_member_loan_type_active is the concurrency/defense-in-
    depth guarantee behind it.
    """
    excluded = set(exclude_loan_ids)
    existing = [
        loan
        for loan in db.query(models.Loan)
        .filter(
            models.Loan.member_id == member_id,
            models.Loan.loan_type_id == loan_type_id,
            models.Loan.status == models.LoanStatus.ACTIVE,
        )
        .all()
        if loan.id not in excluded
    ]
    if not existing:
        return

    loan_type_name = (
        db.query(models.LoanType.name)
        .filter(models.LoanType.id == loan_type_id)
        .scalar()
    )
    raise HTTPException(
        status_code=409,
        detail=(
            "This member already has an active loan of this type"
            f"{f' ({loan_type_name})' if loan_type_name else ''}. "
            "Complete or close it before activating another."
        ),
    )


def assert_member_may_borrow(db: Session, member: models.Member) -> None:
    """New credit is for financial members only.

    Leaving the cooperative doesn't erase an existing loan -- recovery
    keeps running through payroll deductions -- but it does close the door
    on fresh borrowing, so the money can actually be paid back.
    """
    if member.status == models.MemberStatus.FINANCIAL:
        return
    raise HTTPException(
        status_code=409,
        detail=(
            "Non-financial members cannot take out new loans. "
            "Restore financial membership before borrowing again."
        ),
    )


def is_active_loan_type_conflict(error: IntegrityError) -> bool:
    """True when an IntegrityError came from the one-active-loan-per-type index."""
    diag = getattr(getattr(error, "orig", None), "diag", None)
    return getattr(diag, "constraint_name", None) == ACTIVE_LOAN_TYPE_INDEX


def _raise_unless_active_loan_type_conflict(
    db: Session, error: IntegrityError
) -> None:
    db.rollback()
    if not is_active_loan_type_conflict(error):
        raise error
    raise HTTPException(
        status_code=409,
        detail=(
            "This member already has an active loan of this type. "
            "Complete or close it before activating another."
        ),
    )


def flush_or_conflict(db: Session) -> None:
    try:
        db.flush()
    except IntegrityError as error:
        _raise_unless_active_loan_type_conflict(db, error)


def commit_or_conflict(db: Session) -> None:
    """Commit, turning an index conflict into the same 409 the API check raises.

    The application check and the index both exist because two concurrent
    requests can each pass the check before either commits; without this
    the loser would surface as a raw 500.
    """
    try:
        db.commit()
    except IntegrityError as error:
        _raise_unless_active_loan_type_conflict(db, error)
