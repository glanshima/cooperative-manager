"""
Staff/admin user account management -- account lifecycle and
Office/Role assignment (Phase 1, Sections 7-9). This is distinct from
members.py (cooperative member business records) and from
routers/auth.py's create-member-login (which provisions a login for an
existing Member and is left untouched for backward compatibility).
"""
import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import models, schemas, audit_service
from ..account_lifecycle import set_account_status, validate_password_strength
from ..auth import hash_password
from ..database import get_db
from ..deps import get_current_user, require_permission

router = APIRouter(prefix="/api/admin/users", tags=["admin-users"])


@router.get("", response_model=List[schemas.UserOut])
def list_admin_users(
    current_user: models.User = Depends(require_permission("admin.user_manage")),
    db: Session = Depends(get_db),
):
    return (
        db.query(models.User)
        .filter(models.User.role == models.UserRole.ADMIN)
        .order_by(models.User.username)
        .all()
    )


@router.post("", response_model=schemas.UserOut, status_code=201)
def create_admin_user(
    payload: schemas.AdminUserCreate,
    request: Request,
    current_user: models.User = Depends(require_permission("admin.user_manage")),
    db: Session = Depends(get_db),
):
    existing = db.query(models.User).filter(models.User.username == payload.username).first()
    if existing:
        raise HTTPException(status_code=409, detail="A user with this username already exists")

    error = validate_password_strength(payload.password)
    if error:
        raise HTTPException(status_code=400, detail=error)

    user = models.User(
        username=payload.username,
        password_hash=hash_password(payload.password),
        role=models.UserRole.ADMIN,
        must_change_password=True,
        account_status=payload.account_status,
        is_active=payload.account_status == models.AccountStatus.ACTIVE,
        is_super_admin=False,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    audit_service.log_event(
        db,
        actor=current_user,
        event_type="admin.user_created",
        action="create",
        entity_type="user",
        entity_id=str(user.id),
        new_values={"username": user.username, "account_status": user.account_status.value},
        request=request,
    )
    return user


@router.patch("/{user_id}/status", response_model=schemas.UserOut)
def update_admin_user_status(
    user_id: uuid.UUID,
    payload: schemas.AdminUserStatusUpdate,
    request: Request,
    current_user: models.User = Depends(require_permission("admin.user_manage")),
    db: Session = Depends(get_db),
):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.id == current_user.id and payload.account_status != models.AccountStatus.ACTIVE:
        raise HTTPException(status_code=400, detail="You cannot deactivate or suspend your own account")

    previous_status = user.account_status.value
    set_account_status(db, user, payload.account_status, changed_by=current_user, reason=payload.reason)

    # A deactivated/suspended user's outstanding sessions are revoked
    # immediately, so "loses authority" doesn't wait for JWT expiry.
    if payload.account_status != models.AccountStatus.ACTIVE:
        for session in db.query(models.AuthSession).filter(
            models.AuthSession.user_id == user.id, models.AuthSession.revoked_at.is_(None)
        ):
            from datetime import datetime

            session.revoked_at = datetime.utcnow()
            session.revoked_reason = f"account status changed to {payload.account_status.value}"
        db.commit()

    audit_service.log_event(
        db,
        actor=current_user,
        event_type="admin.user_status_changed",
        action="update",
        entity_type="user",
        entity_id=str(user.id),
        previous_values={"account_status": previous_status},
        new_values={"account_status": payload.account_status.value, "reason": payload.reason},
        request=request,
    )
    return user


@router.patch("/{user_id}/member-link", response_model=schemas.UserOut)
def update_admin_user_member_link(
    user_id: uuid.UUID,
    payload: schemas.AdminUserMemberLinkUpdate,
    request: Request,
    current_user: models.User = Depends(require_permission("admin.user_manage")),
    db: Session = Depends(get_db),
):
    """
    Controlled Phase 1 Remediation, Sections 1 and 10: explicitly link
    (or unlink) an admin account to the Member record it belongs to, for
    an elected EXCO officer who is also a cooperative member. This is
    the ONLY way User.member_id is ever set for an admin account -- there
    is no automatic/inferred linking anywhere in the codebase, by design
    (see self_conflict.py's module docstring for why: a wrong inference
    could either wrongly block an unrelated person or, worse, fail to
    catch a real conflict).

    Once linked, self_conflict.require_no_self_conflict() uses this
    field to block this admin from approving, disbursing, verifying, or
    otherwise administratively acting on their own member record or
    financial transactions -- a protection that applies even if this
    admin is a super-admin (see self_conflict.py; super-admin status is
    never checked there).
    """
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.role != models.UserRole.ADMIN:
        raise HTTPException(
            status_code=400,
            detail="Only admin-role accounts can be linked via this endpoint.",
        )

    # Governance Objective 2 (Admin Self-Link Protection): an admin can
    # never use this endpoint to set/change THEIR OWN account's
    # member_id -- decided as a blanket rule (not "only their own
    # existing member"), since allowing an admin to link themselves to
    # SOME OTHER member would let them grant themselves administrative
    # control over their own identity-mapping just as much as linking to
    # "their own" member would. Self-UNLINK (payload.member_id is None)
    # is deliberately NOT blocked here -- removing your own link removes
    # power rather than granting it, and Section 4's separate role-based
    # unlink protection still applies regardless of who performs it.
    # Unconditional: current_user.is_super_admin is never checked, same
    # as every other conflict-of-interest protection in this codebase
    # (self_conflict.py).
    if current_user.id == user_id and payload.member_id is not None:
        audit_service.log_event(
            db,
            actor=current_user,
            event_type="admin.member_link_self_conflict_denied",
            action="deny",
            entity_type="user",
            entity_id=str(user.id),
            reason=f"Blocked: admin attempted to link their own account to member {payload.member_id}.",
            request=request,
        )
        raise HTTPException(
            status_code=409,
            detail={
                "error": "self_conflict",
                "message": (
                    "You cannot link your own account to a Member record. "
                    "Ask another authorized admin to perform this link."
                ),
            },
        )

    previous_member_id = str(user.member_id) if user.member_id else None

    if payload.member_id is not None:
        member = db.query(models.Member).filter(models.Member.id == payload.member_id).first()
        if not member:
            raise HTTPException(status_code=404, detail="Member not found")

        # Friendly pre-check before relying on the partial unique index
        # as a backstop (Section 1: at most one ADMIN-role user per
        # member_id -- a member-role self-service account for the same
        # person, if one exists, is a separate row and unaffected).
        already_linked = (
            db.query(models.User)
            .filter(
                models.User.role == models.UserRole.ADMIN,
                models.User.member_id == payload.member_id,
                models.User.id != user_id,
            )
            .first()
        )
        if already_linked:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Member {payload.member_id} is already linked to another admin "
                    f"account ({already_linked.username})."
                ),
            )
    else:
        # Governance Objective 1, Section 4: do not allow the invalid
        # state (member_id=NULL while an active role.requires_member_link
        # role is held). Only checked when actually clearing a link
        # (payload.member_id is None) and only when the user currently
        # HAS a link to clear -- changing from one member to a different
        # one never passes through this branch, since the resulting
        # member_id is still non-null.
        if user.member_id is not None and _user_has_active_member_required_role(db, user_id):
            raise HTTPException(
                status_code=409,
                detail={
                    "error": "member_link_required",
                    "message": (
                        "This account cannot be unlinked from its Member because it holds "
                        "an active role that requires Member linkage. Change or revoke "
                        "that role first."
                    ),
                },
            )

    user.member_id = payload.member_id
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="This member is already linked to another admin account.",
        )
    db.refresh(user)

    audit_service.log_event(
        db,
        actor=current_user,
        event_type="admin.user_member_link_changed",
        action="update",
        entity_type="user",
        entity_id=str(user.id),
        previous_values={"member_id": previous_member_id},
        new_values={"member_id": str(user.member_id) if user.member_id else None},
        reason=payload.reason,
        request=request,
    )
    return user


@router.get("/{user_id}/assignments", response_model=List[schemas.UserRoleAssignmentOut])
def list_user_assignments(
    user_id: uuid.UUID,
    current_user: models.User = Depends(require_permission("admin.role_manage")),
    db: Session = Depends(get_db),
):
    assignments = (
        db.query(models.UserRoleAssignment)
        .filter(models.UserRoleAssignment.user_id == user_id)
        .all()
    )
    return [_to_assignment_out(a) for a in assignments]


def _user_has_active_member_required_role(db: Session, user_id: uuid.UUID) -> bool:
    """
    Admin Identity Governance remediation, Governance Objective 1
    (Sections 3-5): true if `user_id` currently holds at least one
    ACTIVE role assignment whose Role has requires_member_link=True.
    Mirrors the exact active-assignment convention already used by
    deps.py::user_has_permission (UserRoleAssignment.is_active AND
    Role.is_active), so "active" means the same thing here as it does
    everywhere else permission/role state is checked in this codebase.
    """
    return (
        db.query(models.UserRoleAssignment)
        .join(models.Role, models.UserRoleAssignment.role_id == models.Role.id)
        .filter(
            models.UserRoleAssignment.user_id == user_id,
            models.UserRoleAssignment.is_active.is_(True),
            models.Role.is_active.is_(True),
            models.Role.requires_member_link.is_(True),
        )
        .first()
        is not None
    )


@router.post("/{user_id}/assignments", response_model=schemas.UserRoleAssignmentOut, status_code=201)
def assign_role(
    user_id: uuid.UUID,
    payload: schemas.UserRoleAssignmentCreate,
    request: Request,
    current_user: models.User = Depends(require_permission("admin.role_manage")),
    db: Session = Depends(get_db),
):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user or user.role != models.UserRole.ADMIN:
        raise HTTPException(status_code=404, detail="Admin user not found")
    role = db.query(models.Role).filter(models.Role.id == payload.role_id).first()
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")
    if payload.office_id:
        office = db.query(models.Office).filter(models.Office.id == payload.office_id).first()
        if not office:
            raise HTTPException(status_code=404, detail="Office not found")

    # Governance Objective 1, Section 3: a role marked requires_member_link
    # cannot be assigned to an account with no linked Member. Backend-
    # authoritative -- enforced here regardless of caller (UI, direct API
    # call, future client).
    if role.requires_member_link and user.member_id is None:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "member_link_required",
                "message": (
                    "This role requires the user account to be linked to a Member "
                    "before the role can be assigned."
                ),
            },
        )

    assignment = models.UserRoleAssignment(
        user_id=user_id,
        role_id=payload.role_id,
        office_id=payload.office_id,
        assigned_by_user_id=current_user.id,
    )
    db.add(assignment)
    db.commit()
    db.refresh(assignment)

    audit_service.log_event(
        db,
        actor=current_user,
        event_type="admin.role_assigned",
        action="create",
        entity_type="user_role_assignment",
        entity_id=str(assignment.id),
        new_values={"user_id": str(user_id), "role": role.name},
        request=request,
    )
    return _to_assignment_out(assignment)


@router.delete("/{user_id}/assignments/{assignment_id}", status_code=204)
def revoke_role(
    user_id: uuid.UUID,
    assignment_id: uuid.UUID,
    request: Request,
    current_user: models.User = Depends(require_permission("admin.role_manage")),
    db: Session = Depends(get_db),
):
    assignment = (
        db.query(models.UserRoleAssignment)
        .filter(models.UserRoleAssignment.id == assignment_id, models.UserRoleAssignment.user_id == user_id)
        .first()
    )
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found")

    from datetime import datetime

    assignment.is_active = False
    assignment.revoked_at = datetime.utcnow()
    assignment.revoked_by_user_id = current_user.id
    db.commit()

    audit_service.log_event(
        db,
        actor=current_user,
        event_type="admin.role_revoked",
        action="update",
        entity_type="user_role_assignment",
        entity_id=str(assignment.id),
        request=request,
    )
    return None


def _to_assignment_out(a: models.UserRoleAssignment) -> schemas.UserRoleAssignmentOut:
    return schemas.UserRoleAssignmentOut(
        id=a.id,
        user_id=a.user_id,
        role_id=a.role_id,
        role_name=a.role.name if a.role else "",
        office_id=a.office_id,
        office_name=a.office.name if a.office else None,
        is_active=a.is_active,
        assigned_at=a.assigned_at,
        revoked_at=a.revoked_at,
    )
