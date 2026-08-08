import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import or_

from .. import models, schemas
from ..database import get_db

router = APIRouter(prefix="/api/members", tags=["members"])


@router.get("", response_model=List[schemas.MemberOut])
def list_members(
    search: Optional[str] = Query(None, description="Search by name or PSN"),
    status: Optional[models.MemberStatus] = None,
    skip: int = 0,
    limit: int = 100,
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
def get_member(member_id: uuid.UUID, db: Session = Depends(get_db)):
    member = db.query(models.Member).filter(models.Member.id == member_id).first()
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")
    return member


@router.post("", response_model=schemas.MemberOut, status_code=201)
def create_member(payload: schemas.MemberCreate, db: Session = Depends(get_db)):
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
    member_id: uuid.UUID, payload: schemas.MemberUpdate, db: Session = Depends(get_db)
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
def delete_member(member_id: uuid.UUID, db: Session = Depends(get_db)):
    member = db.query(models.Member).filter(models.Member.id == member_id).first()
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")

    db.delete(member)
    db.commit()
    return None
