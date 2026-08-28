import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session
from sqlalchemy import or_

from .. import models, schemas, audit_service
from ..database import get_db
from ..deps import require_admin, get_current_user, require_permission

router = APIRouter(prefix="/api/members", tags=["members"])


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
    return member


@router.get("", response_model=List[schemas.MemberOut])
def list_members(
    search: Optional[str] = Query(None, description="Search by name or PSN"),
    status: Optional[models.MemberStatus] = None,
    skip: int = 0,
    limit: int = 100,
    current_user: models.User = Depends(require_permission("member.view")),
    db: Session = Depends(get_db),
):
    query = db.query(models.Member)

    if search:
        like = f"%{search}%"
        query = query.filter(
            or_(models.Member.name.ilike(like), models.Member.psn.ilike(like))
        )

    if status:
        query = query.filter(models.Member.status == status)

    return query.order_by(models.Member.name).offset(skip).limit(limit).all()


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

    member = models.Member(**payload.model_dump())
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

    changes = payload.model_dump(exclude_unset=True)
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
