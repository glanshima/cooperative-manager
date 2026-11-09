"""The member's monthly contribution -- the savings instalment payroll
deducts every month.

Member.monthly_contribution_amount is the agreed figure; this module owns
the rules about who may have one and which payroll month it applies to.
The deduction expectation engine and the contribution-change review flow
both read those rules from here, so they can never disagree about what a
member owes for a given month.
"""
import uuid
from datetime import date
from decimal import Decimal
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from . import models


def month_start(value: date) -> date:
    return value.replace(day=1)


def next_month_start(value: date) -> date:
    if value.month == 12:
        return date(value.year + 1, 1, 1)
    return date(value.year, value.month + 1, 1)


def assert_may_have_contribution(member: models.Member) -> None:
    """A contribution line IS a savings entry, and only financial members
    owe one -- the same rule the deduction router enforces on the lines
    themselves (see _assert_contribution_line_matches_membership)."""
    assert_status_may_have_contribution(member.status)


def assert_status_may_have_contribution(status: models.MemberStatus) -> None:
    """The status-level form, for callers validating a prospective status
    (an edit that reactivates a member and records their contribution in
    the same request) rather than the one currently stored."""
    if status == models.MemberStatus.FINANCIAL:
        return
    raise HTTPException(
        status_code=400,
        detail=(
            "Only financial members have a monthly contribution. Record anything "
            "a non-financial member owes as an 'other' deduction."
        ),
    )


def amount_for_month(db: Session, member: models.Member, month: date) -> Optional[Decimal]:
    """What this member owes as a contribution for a payroll month, or None
    when no contribution line applies.

    None covers three cases: non-financial members (which includes everyone
    who has exited), members with no amount on file yet, and months before
    any amount took effect.

    An approved change is never retroactive, so a month BEFORE the stored
    amount's effective date must still be priced at the figure that was in
    force then -- officers do enter a payroll month late. Member only holds
    the current figure; the one it replaced survives as the current_amount
    snapshot on the request that moved away from it, and the earliest
    approved change taking effect after `month` is exactly the change that
    ended the amount applicable to `month`. Two approvals in the same
    calendar month share an effective date; reviewed_at breaks that tie so
    the later decision supersedes the earlier one.
    """
    if member.status != models.MemberStatus.FINANCIAL:
        return None
    amount = member.monthly_contribution_amount
    if amount is None:
        return None

    month = month_start(month)
    effective = member.contribution_effective_from
    if effective is None or effective <= month:
        return amount

    superseded_by = (
        db.query(models.ContributionChangeRequest)
        .filter(
            models.ContributionChangeRequest.member_id == member.id,
            models.ContributionChangeRequest.status
            == models.ContributionChangeRequestStatus.APPROVED,
            models.ContributionChangeRequest.effective_from > month,
        )
        .order_by(
            models.ContributionChangeRequest.effective_from.asc(),
            models.ContributionChangeRequest.reviewed_at.asc(),
        )
        .first()
    )
    return superseded_by.current_amount if superseded_by else None


def pending_request(
    db: Session, member_id: uuid.UUID
) -> Optional[models.ContributionChangeRequest]:
    return (
        db.query(models.ContributionChangeRequest)
        .filter(
            models.ContributionChangeRequest.member_id == member_id,
            models.ContributionChangeRequest.status
            == models.ContributionChangeRequestStatus.PENDING,
        )
        .first()
    )