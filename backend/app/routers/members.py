import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session
from sqlalchemy import or_

from .. import models, schemas, audit_service, member_relationships
from ..database import get_db
from ..deps import require_admin, get_current_user, require_permission
from ..self_conflict import require_no_self_conflict

router = APIRouter(prefix="/api/members", tags=["members"])


def _attach_next_of_kin(db: Session, members: List[models.Member]) -> None:
    """
    Member Relationship / Next-of-Kin Controlled Remediation (2026-09):
    populate the (non-persisted, request-scoped) next_of_kin_is_member/
    next_of_kin_member attributes that MemberOut serializes, from a
    single bulk query -- same pattern as _attach_login_state above.

    next_of_kin_is_member is set to True when an active relationship
    exists, False when one doesn't but the legacy free-text next_of_kin
    field is populated (an already-answered "no" in substance, even
    though this remediation didn't exist when it was entered), and left
    None only when neither a relationship nor any free-text Next-of-Kin
    data exists at all -- i.e. genuinely never answered. This mirrors
    login_account_status's None-means-unknown convention above rather
    than forcing every pre-existing member into an artificial
    True/False.
    """
    if not members:
        return
    member_ids = [m.id for m in members]
    active_relationships = (
        db.query(models.MemberRelationship)
        .filter(
            models.MemberRelationship.member_id.in_(member_ids),
            models.MemberRelationship.relationship_type == models.RelationshipType.NEXT_OF_KIN,
            models.MemberRelationship.status == models.RelationshipStatus.ACTIVE,
        )
        .all()
    )
    by_member_id = {r.member_id: r for r in active_relationships}
    related_member_ids = [r.related_member_id for r in active_relationships]
    related_members_by_id = {}
    if related_member_ids:
        related_members_by_id = {
            m.id: m
            for m in db.query(models.Member).filter(models.Member.id.in_(related_member_ids)).all()
        }

    for member in members:
        rel = by_member_id.get(member.id)
        if rel is not None:
            member.next_of_kin_is_member = True
            member.next_of_kin_member = related_members_by_id.get(rel.related_member_id)
        elif member.next_of_kin:
            member.next_of_kin_is_member = False
            member.next_of_kin_member = None
        else:
            member.next_of_kin_is_member = None
            member.next_of_kin_member = None


def _attach_login_state(db: Session, members: List[models.Member]) -> None:
    """
    Login State Reconciliation Addendum: populate the (non-persisted,
    request-scoped) login_user_id/login_account_status attributes that
    MemberOut serializes, from a single bulk query -- this is the ONE
    place the Members table's login-action state is computed, so the
    frontend never has to (and never did correctly -- see the addendum's
    root-cause finding: MemberOut previously carried no login-state
    information at all, and the "Create login" button was rendered
    unconditionally for every row regardless of whether a login already
    existed).

    Scoped to role == MEMBER deliberately: a member's *self-service* PSN
    login is a different account from an admin-role account that might
    also be linked to the same member_id for conflict-of-interest
    purposes (see self_conflict.py / Controlled Remediation Section 1)
    -- an EXCO officer having an admin account does not mean they
    already have their own member self-service login, and this must not
    be conflated.
    """
    if not members:
        return
    member_ids = [m.id for m in members]
    member_logins = (
        db.query(models.User)
        .filter(models.User.member_id.in_(member_ids), models.User.role == models.UserRole.MEMBER)
        .all()
    )
    by_member_id = {u.member_id: u for u in member_logins}
    for member in members:
        login_user = by_member_id.get(member.id)
        member.login_user_id = login_user.id if login_user else None
        member.login_account_status = login_user.account_status if login_user else None


@router.get("/me", response_model=schemas.MemberOut)
def get_my_member_record(
    current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """Convenience endpoint for a logged-in member's own dashboard, so the
    frontend doesn't need to know its own member_id up front."""
    if current_user.role != models.UserRole.MEMBER or not current_user.member_id:
        raise HTTPException(status_code=403, detail="Only members have a member record")
    member = db.query(models.Member).filter(models.Member.id == current_user.member_id).first()
    if not member:
        raise HTTPException(status_code=404, detail="Member record not found")
    _attach_next_of_kin(db, [member])
    return member


@router.get("/filter-options", response_model=schemas.MemberFilterOptions)
def get_member_filter_options(
    current_user: models.User = Depends(require_permission("member.view")),
    db: Session = Depends(get_db),
):
    """
    Members Search & Filtering Remediation, Sections 6/7/14: populates
    the Bank/Department filter dropdowns from DISTINCT values actually
    present on authorized members right now -- never fabricated, never
    hard-coded. There is no separate Bank or Department entity in this
    codebase (bank_name/department are free-text columns on Member); see
    the Phase 1 report for that finding and why introducing one was out
    of scope for this remediation.
    """
    banks = (
        db.query(models.Member.bank_name)
        .filter(models.Member.bank_name.isnot(None), models.Member.bank_name != "")
        .distinct()
        .order_by(models.Member.bank_name)
        .all()
    )
    departments = (
        db.query(models.Member.department)
        .filter(models.Member.department.isnot(None), models.Member.department != "")
        .distinct()
        .order_by(models.Member.department)
        .all()
    )
    return schemas.MemberFilterOptions(
        banks=[b[0] for b in banks],
        departments=[d[0] for d in departments],
    )


@router.get("", response_model=schemas.MemberListResponse)
def list_members(
    search: Optional[str] = Query(None, description="Matches member number/PSN, name, or phone"),
    bank_name: Optional[str] = Query(None, description="Exact match against Member.bank_name"),
    department: Optional[str] = Query(None, description="Exact match against Member.department"),
    status: Optional[models.MemberStatus] = None,
    skip: int = 0,
    limit: int = 100,
    current_user: models.User = Depends(require_permission("member.view")),
    db: Session = Depends(get_db),
):
    """
    Members Search & Filtering Remediation (2026-08-29). Two
    conceptually separate, combinable mechanisms, both enforced here at
    the query level (never in the browser, never against only the
    current page):

    - Free-text `search` -- "which member(s) am I looking for" -- matches
      PSN (this codebase's Member Number/ID -- there is no separate
      member_number field; see the Phase 1 report), name, or phone.
      Normalized server-side: `.strip()`ed, and empty/whitespace-only
      input is treated as no search at all (never sent to the DB as an
      empty-string LIKE). Leading/trailing whitespace on the STORED
      value is not a concern here -- this only trims the incoming query
      term. Meaningful internal spaces (e.g. "John Doe") are preserved,
      since `.strip()` only removes leading/trailing whitespace.
      Email is deliberately NOT included: it was never part of the
      pre-existing search contract (the prior implementation only
      matched name/PSN), and this remediation's own scope note makes
      email-search conditional on it already being approved -- it
      wasn't, so it stays out.
    - Structured filters `bank_name`, `department`, `status` -- "which
      group of members do I want to see" -- each optional and
      independently usable without `search`. `status` uses this
      codebase's actual canonical MemberStatus values (`financial` /
      `non_financial` -- there is no `active`/`inactive` status in this
      data model; see the Phase 1 report for why the addendum's
      "Active"/"Inactive" wording maps to these instead of being
      invented as new values).

    All conditions AND together. `total` in the response is the count of
    the FULLY FILTERED dataset (before `skip`/`limit` are applied), so
    the frontend can compute total pages and detect an out-of-range page
    after a filter change -- this is why the endpoint returns
    MemberListResponse instead of a bare list.
    """
    query = db.query(models.Member)

    normalized_search = search.strip() if search else ""
    if normalized_search:
        like = f"%{normalized_search}%"
        query = query.filter(
            or_(
                models.Member.name.ilike(like),
                models.Member.psn.ilike(like),
                models.Member.phone.ilike(like),
            )
        )

    if bank_name:
        query = query.filter(models.Member.bank_name == bank_name)

    if department:
        query = query.filter(models.Member.department == department)

    if status:
        query = query.filter(models.Member.status == status)

    total = query.count()
    members = query.order_by(models.Member.name).offset(skip).limit(limit).all()
    _attach_login_state(db, members)
    _attach_next_of_kin(db, members)
    return schemas.MemberListResponse(items=members, total=total, skip=skip, limit=limit)


@router.get("/{member_id}", response_model=schemas.MemberOut)
def get_member(
    member_id: uuid.UUID,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # Object-level authorization (Section 11): a member may only ever
    # fetch their own record by ID substitution; admins additionally need
    # member.view. This check happens before the DB lookup result is
    # returned regardless of whether the ID exists, so response shape
    # doesn't leak existence to an unauthorized member.
    if current_user.role == models.UserRole.MEMBER:
        if current_user.member_id != member_id:
            raise HTTPException(status_code=403, detail="You can only view your own record")
    else:
        from ..deps import user_has_permission

        if not user_has_permission(db, current_user, "member.view"):
            raise HTTPException(status_code=403, detail="You do not have the 'member.view' permission")

    member = db.query(models.Member).filter(models.Member.id == member_id).first()
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")
    _attach_login_state(db, [member])
    _attach_next_of_kin(db, [member])
    return member


@router.post("", response_model=schemas.MemberOut, status_code=201)
def create_member(
    payload: schemas.MemberCreate,
    request: Request,
    current_user: models.User = Depends(require_permission("member.create")),
    db: Session = Depends(get_db),
):
    existing = db.query(models.Member).filter(models.Member.psn == payload.psn).first()
    if existing:
        raise HTTPException(status_code=409, detail="A member with this PSN already exists")

    # next_of_kin_is_member / next_of_kin_member_id (Member Relationship
    # / Next-of-Kin Controlled Remediation, Section 1) aren't Member
    # columns -- they're consumed below to create a MemberRelationship
    # row instead, so they're popped out of the dict passed to the
    # Member(**...) constructor.
    payload_data = payload.model_dump()
    next_of_kin_is_member = payload_data.pop("next_of_kin_is_member")
    next_of_kin_member_id = payload_data.pop("next_of_kin_member_id")

    member = models.Member(**payload_data)
    db.add(member)
    db.commit()
    db.refresh(member)

    audit_service.log_event(
        db,
        actor=current_user,
        event_type="member.created",
        action="create",
        entity_type="member",
        entity_id=str(member.id),
        new_values={"psn": member.psn, "name": member.name},
        request=request,
    )

    if next_of_kin_is_member:
        member_relationships.set_relationship(
            db,
            member=member,
            related_member_id=next_of_kin_member_id,
            actor=current_user,
            request=request,
        )

    _attach_next_of_kin(db, [member])
    return member


@router.put("/{member_id}", response_model=schemas.MemberOut)
def update_member(
    member_id: uuid.UUID,
    payload: schemas.MemberUpdate,
    request: Request,
    current_user: models.User = Depends(require_permission("member.update")),
    db: Session = Depends(get_db),
):
    member = db.query(models.Member).filter(models.Member.id == member_id).first()
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")

    require_no_self_conflict(
        db,
        current_user,
        member,
        action_description="administratively edit your own member record",
        permission_code="member.update",
        entity_type="member",
        entity_id=str(member.id),
        request=request,
    )

    changes = payload.model_dump(exclude_unset=True)

    # next_of_kin_is_member / next_of_kin_member_id (Member Relationship
    # / Next-of-Kin Controlled Remediation, Section 8) aren't Member
    # columns -- pop them out before the generic setattr loop below,
    # and apply the relationship transition separately via
    # member_relationships.py. `"next_of_kin_is_member" in changes`
    # (i.e. it was actually sent, via exclude_unset=True above) is what
    # decides whether the Next-of-Kin relationship is touched at all --
    # not whether its value is truthy -- so an ordinary edit that never
    # mentions Next of Kin leaves the existing relationship (or lack of
    # one) completely alone.
    next_of_kin_is_member = changes.pop("next_of_kin_is_member", "unset")
    next_of_kin_member_id = changes.pop("next_of_kin_member_id", None)

    previous = {field: getattr(member, field) for field in changes}
    for field, value in changes.items():
        setattr(member, field, value)

    db.commit()
    db.refresh(member)

    audit_service.log_event(
        db,
        actor=current_user,
        event_type="member.updated",
        action="update",
        entity_type="member",
        entity_id=str(member.id),
        previous_values=previous,
        new_values=changes,
        request=request,
    )

    if next_of_kin_is_member is True:
        member_relationships.set_relationship(
            db,
            member=member,
            related_member_id=next_of_kin_member_id,
            actor=current_user,
            request=request,
        )
    elif next_of_kin_is_member is False:
        member_relationships.clear_relationship(db, member=member, actor=current_user, request=request)

    _attach_next_of_kin(db, [member])
    return member


@router.patch("/{member_id}/login-status", response_model=schemas.MemberOut)
def update_member_login_status(
    member_id: uuid.UUID,
    payload: schemas.MemberLoginStatusUpdate,
    request: Request,
    current_user: models.User = Depends(require_permission("member.deactivate")),
    db: Session = Depends(get_db),
):
    """
    Login State Reconciliation Addendum (2026-08-29): deactivate or
    reactivate a member's EXISTING self-service login. This is the
    endpoint the Members table's "Deactivate Login" / "Reactivate Login"
    action calls -- distinct from POST /api/auth/create-member-login
    (which only handles the no-login-yet case) and from deleting the
    Member record entirely (which this never does -- see delete_member's
    docstring, Change-Control C-2: the Member and User rows, and all
    financial/audit history, are preserved regardless of login status).

    Reuses member.deactivate rather than introducing a new permission
    code -- login lifecycle for a member is squarely what that
    permission already covers (see its use in delete_member above).
    """
    member = db.query(models.Member).filter(models.Member.id == member_id).first()
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")

    login_user = (
        db.query(models.User)
        .filter(models.User.member_id == member_id, models.User.role == models.UserRole.MEMBER)
        .first()
    )
    if not login_user:
        raise HTTPException(
            status_code=404,
            detail="This member doesn't have a login yet. Use Create Login instead.",
        )

    require_no_self_conflict(
        db,
        current_user,
        member,
        action_description="change your own login's active status",
        permission_code="member.deactivate",
        entity_type="member",
        entity_id=str(member.id),
        request=request,
    )

    previous_status = login_user.account_status.value
    from ..account_lifecycle import set_account_status

    set_account_status(db, login_user, payload.account_status, changed_by=current_user, reason=payload.reason)

    # Mirrors admin_users.py's status-change behavior: a deactivated/
    # suspended login's outstanding sessions are revoked immediately, so
    # "loses access" doesn't wait for JWT expiry.
    if payload.account_status != models.AccountStatus.ACTIVE:
        from datetime import datetime as _datetime

        for session in db.query(models.AuthSession).filter(
            models.AuthSession.user_id == login_user.id, models.AuthSession.revoked_at.is_(None)
        ):
            session.revoked_at = _datetime.utcnow()
            session.revoked_reason = f"member login status changed to {payload.account_status.value}"
        db.commit()

    audit_service.log_event(
        db,
        actor=current_user,
        event_type="member.login_status_changed",
        action="update",
        entity_type="user",
        entity_id=str(login_user.id),
        previous_values={"account_status": previous_status},
        new_values={"account_status": payload.account_status.value, "reason": payload.reason},
        request=request,
    )

    _attach_login_state(db, [member])
    return member


@router.delete("/{member_id}", status_code=204)
def delete_member(
    member_id: uuid.UUID,
    request: Request,
    current_user: models.User = Depends(require_permission("member.deactivate")),
    db: Session = Depends(get_db),
):
    """
    Change-Control note (C-2, see Phase 1 implementation report): the
    original endpoint performed a hard delete that CASCADEs to the
    member's loans/loan_applications (delete-orphan), which would
    physically destroy posted financial history -- a direct conflict
    with Section 15 (Financial History Protection: "Do not physically
    delete posted financial transactions"). No explicit member-deletion
    policy was specified for this case, so rather than inventing one
    silently, the safe interpretation is applied here: hard delete is
    only permitted when the member has zero financial history (no
    loans, no loan applications); otherwise the record is deactivated
    (status set to NON_FINANCIAL preserved as-is, login access revoked)
    instead of deleted, and the caller is told why. A formal
    member-lifecycle status model (Section 7-style pending/active/
    suspended/deactivated for Member, not just User) is deferred to
    Phase 2 per the master audit's finding M1-004.
    """
    member = db.query(models.Member).filter(models.Member.id == member_id).first()
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")

    require_no_self_conflict(
        db,
        current_user,
        member,
        action_description="deactivate or delete your own member record",
        permission_code="member.deactivate",
        entity_type="member",
        entity_id=str(member.id),
        request=request,
    )

    has_financial_history = bool(member.loans) or bool(member.loan_applications)
    if has_financial_history:
        raise HTTPException(
            status_code=409,
            detail=(
                "This member has loan or loan-application history and cannot be deleted. "
                "Revoke their login instead (see admin.user_manage on their linked user account)."
            ),
        )

    audit_service.log_event(
        db,
        actor=current_user,
        event_type="member.deleted",
        action="delete",
        entity_type="member",
        entity_id=str(member.id),
        previous_values={"psn": member.psn, "name": member.name},
        request=request,
    )

    db.delete(member)
    db.commit()
    return None
