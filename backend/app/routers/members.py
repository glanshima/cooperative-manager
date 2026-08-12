import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import or_

from .. import models, schemas
from ..database import get_db
from ..deps import require_admin, get_current_user

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
    current_user: models.User = Depends(require_admin),
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
    if current_user.role == models.UserRole.MEMBER and current_user.member_id != member_id:
        raise HTTPException(status_code=403, detail="You can only view your own record")
    member = db.query(models.Member).filter(models.Member.id == member_id).first()
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")
    return member


@router.post("", response_model=schemas.MemberOut, status_code=201)
def create_member(
    payload: schemas.MemberCreate,
    current_user: models.User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    existing = db.query(models.Member).filter(models.Member.psn == payload.psn).first()
    if existing:
        raise HTTPException(status_code=409, detail="A member with this PSN already exists")

    member = models.Member(**payload.model_dump())
    db.add(member)
    db.commit()
    db.refresh(member)
    return member


@router.put("/{member_id}", response_model=schemas.MemberOut)
def update_member(
    member_id: uuid.UUID,
    payload: schemas.MemberUpdate,
    current_user: models.User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    member = db.query(models.Member).filter(models.Member.id == member_id).first()
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(member, field, value)

    db.commit()
    db.refresh(member)
    return member


@router.delete("/{member_id}", status_code=204)
def delete_member(
    member_id: uuid.UUID,
    current_user: models.User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    member = db.query(models.Member).filter(models.Member.id == member_id).first()
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")

    db.delete(member)
    db.commit()
    return None
