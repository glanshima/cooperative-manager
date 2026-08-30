"""
Member-link governance guard.

Controlled Implementation -- Admin Governance & Member-Link Enforcement
(2026-08), Sections 2-4: an admin account must not receive a permission
classified `requires_member_link=True` (see permissions_catalogue.py)
unless it is either:

  A. linked to the Member it represents (User.member_id is set), so
     self_conflict.py can actually detect if this officer is acting on
     their own money, or
  B. explicitly confirmed as a legitimate non-member account
     (User.confirmed_non_member_admin), an affirmative, audited
     attestation set by another admin.user_manage holder -- NEVER
     inferred, same design rule as member_id itself.

This is enforced server-side at both places a sensitive permission can
reach an account: granting a new role assignment
(routers/admin_users.py::assign_role) and editing an existing role's
permission set while it's already assigned to someone
(routers/roles.py::update_role). Frontend validation is not a
substitute for either.

This module intentionally does not touch self_conflict.py -- self-dealing
prevention (blocking action on one's OWN record) and member-link
governance (whether an unlinked account may hold the permission at all)
are separate change-control concerns and must not be conflated.
"""
from typing import Iterable

from sqlalchemy.orm import Session

from . import models


def sensitive_codes_in(db: Session, permission_codes: Iterable[str]) -> list:
    """Return the subset of `permission_codes` that are classified
    requires_member_link=True in the Permission table (the DB-seeded
    mirror of PERMISSION_CATALOGUE -- see permissions_catalogue.py)."""
    codes = list(permission_codes)
    if not codes:
        return []
    rows = (
        db.query(models.Permission.code)
        .filter(models.Permission.code.in_(codes), models.Permission.requires_member_link.is_(True))
        .all()
    )
    return [code for (code,) in rows]


def is_governance_satisfied(user: models.User) -> bool:
    """True if `user` is allowed to hold a sensitive financial
    permission: either linked to a Member, or explicitly confirmed as a
    legitimate non-member account. Fail-closed otherwise."""
    return user.member_id is not None or user.confirmed_non_member_admin


def governance_denial_message(user: models.User, blocking_codes: list) -> str:
    return (
        f"Cannot grant permission(s) {', '.join(sorted(blocking_codes))} to "
        f"'{user.username}': these require the account to be linked to the "
        "Member it represents (member-link), or explicitly confirmed as a "
        "legitimate non-member admin account, before they can be held. "
        "Link the account via PATCH /api/admin/users/{id}/member-link, or "
        "confirm it via PATCH /api/admin/users/{id}/non-member-confirmation."
    )
