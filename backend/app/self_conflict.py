"""
Central conflict-of-interest guard.

Controlled Phase 1 Remediation (2026-08), Sections 1-8: MACT cooperative
members are elected EXCO officers -- the same physical person can hold
both a Member record (they take out loans, make repayments) and an
admin/staff User account with real permissions (loan.approve,
disbursement.submit, etc.). Holding a permission authorizes a user to
act generally; it does NOT authorize them to act on their OWN member
record or their OWN financial transactions. This module is the single,
reusable place that boundary is enforced, so it isn't reimplemented
(and potentially gotten wrong, or forgotten) separately in every router.

DESIGN
------
`User.member_id` (an existing nullable FK, see models.py) is the one and
only source of truth for "this admin account belongs to this member."
It is NEVER inferred from name, email, phone number, or any other
fuzzy/heuristic match -- Section 1 of the remediation prompt explicitly
forbids that, because a wrong inference here would either (a) block a
legitimate action for an unrelated person who happens to share a name,
or worse (b) fail to block a real conflict because the heuristic missed
it. If `current_user.member_id` is NULL, this module always treats the
user as having no conflict -- no attempt is made to guess one.

This check is UNCONDITIONAL. is_super_admin does not bypass it (Section
4: "Super-admin must NOT bypass self-record/conflict-of-interest
protection"). It is intentionally implemented as a plain function called
explicitly by each router at the point the target member is known --
NOT folded into user_has_permission()/require_permission() -- so there
is no path where "holds a permission" alone can satisfy it, and no
single shared dependency that a future endpoint could accidentally omit
without it being visible in that endpoint's own code.
"""
import uuid
from typing import Iterable, Optional, Union

from fastapi import HTTPException, Request
from sqlalchemy.orm import Session

from . import audit_service, models

MemberLike = Union[
    None,
    uuid.UUID,
    str,
    "models.Member",
    "models.LoanApplication",
    "models.Loan",
    "models.LoanRepayment",
]


def resolve_owning_member_id(db: Session, target: MemberLike) -> Optional[uuid.UUID]:
    """
    Resolve the Member a given object belongs to, including indirectly
    (Section 6 -- object ownership, direct and indirect):
      Member                       -> itself
      LoanApplication, Loan        -> .member_id (direct FK)
      LoanRepayment                -> .loan.member_id (via the loan)
      raw UUID/str                 -> parsed as a member_id directly
      None                         -> None
    """
    if target is None:
        return None
    if isinstance(target, uuid.UUID):
        return target
    if isinstance(target, str):
        return uuid.UUID(target)
    if isinstance(target, models.Member):
        return target.id
    if isinstance(target, (models.LoanApplication, models.Loan)):
        return target.member_id
    if isinstance(target, models.LoanRepayment):
        # LoanRepayment carries its own member_id column directly
        # (denormalized alongside loan_id) -- use it rather than going
        # through .loan, so this works even when the relationship wasn't
        # eagerly loaded.
        return target.member_id
    raise TypeError(f"resolve_owning_member_id: unsupported target type {type(target)!r}")


def find_eligible_approvers(
    db: Session,
    conflicted_member_id: Optional[uuid.UUID],
    permission_code: str,
    *,
    exclude_user_ids: Iterable[uuid.UUID] = (),
) -> list:
    """
    Return active admin Users who hold `permission_code` and are NOT
    conflicted against `conflicted_member_id` (Section 5 -- alternate
    approval path). Purely informational: this is used to give a useful
    "here's who else can do this" answer instead of a dead end. It never
    auto-assigns, auto-approves, or reroutes the action itself.
    """
    # Local import to avoid a circular import (deps.py doesn't need to
    # know about self_conflict.py; this module already depends on
    # models.py directly for the permission-check query below).
    from .deps import user_has_permission

    exclude_ids = set(exclude_user_ids)
    candidates = (
        db.query(models.User)
        .filter(
            models.User.role == models.UserRole.ADMIN,
            models.User.account_status == models.AccountStatus.ACTIVE,
        )
        .all()
    )
    eligible = []
    for candidate in candidates:
        if candidate.id in exclude_ids:
            continue
        if (
            conflicted_member_id is not None
            and candidate.member_id is not None
            and candidate.member_id == conflicted_member_id
        ):
            continue
        if user_has_permission(db, candidate, permission_code):
            eligible.append(candidate)
    return eligible


def require_no_self_conflict(
    db: Session,
    current_user: models.User,
    target: MemberLike,
    *,
    action_description: str,
    permission_code: Optional[str] = None,
    entity_type: Optional[str] = None,
    entity_id: Optional[str] = None,
    request: Optional[Request] = None,
) -> None:
    """
    Raise HTTP 409 if `current_user` is administratively acting on their
    own member record or a financial object that belongs to them.

    - `action_description`: short human-readable phrase for the error
      message, e.g. "approve or reject this loan application".
    - `permission_code`: if given, eligible alternate approvers (Section
      5) are looked up and included in the error response so the caller
      isn't left at a dead end.
    - `entity_type`/`entity_id`/`request`: if given, the denial itself is
      audit-logged (Section 8) with actor, actor's linked member, action,
      target, and reason -- never credentials.

    No-ops (returns without raising) when `current_user.member_id` is
    NULL, or when the target has no resolvable owning member (e.g. a
    brand-new record not yet tied to anyone).
    """
    if current_user.member_id is None:
        return

    target_member_id = resolve_owning_member_id(db, target)
    if target_member_id is None:
        return

    if target_member_id != current_user.member_id:
        return

    eligible_approvers = []
    if permission_code:
        eligible_approvers = find_eligible_approvers(
            db,
            target_member_id,
            permission_code,
            exclude_user_ids=[current_user.id],
        )

    if entity_type is not None:
        audit_service.log_event(
            db,
            actor=current_user,
            event_type="conflict_of_interest.denied",
            action="deny",
            entity_type=entity_type,
            entity_id=entity_id,
            reason=f"Blocked: attempted to {action_description} on own member record.",
            request=request,
        )

    raise HTTPException(
        status_code=409,
        detail={
            "error": "self_conflict",
            "message": (
                f"You cannot {action_description} because it belongs to you "
                "This action requires another eligible officer."
            ),
            "eligible_approvers": [
                {"id": str(u.id), "username": u.username} for u in eligible_approvers
            ],
            "no_eligible_approver_available": bool(permission_code) and not eligible_approvers,
        },
    )
