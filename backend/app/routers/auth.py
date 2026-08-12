import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas
from ..auth import hash_password, verify_password, create_access_token
from ..database import get_db
from ..deps import get_current_user, require_admin

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=schemas.LoginResponse)
def login(payload: schemas.LoginRequest, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.username == payload.username).first()

    invalid = HTTPException(status_code=401, detail="Invalid username or password")

    if not user or not user.is_active:
        raise invalid
    if not verify_password(payload.password, user.password_hash):
        raise invalid

    token = create_access_token(user_id=str(user.id), role=user.role.value)
    return schemas.LoginResponse(
        access_token=token,
        role=user.role,
        must_change_password=user.must_change_password,
    )


@router.post("/change-password", response_model=schemas.UserOut)
def change_password(
    payload: schemas.ChangePasswordRequest,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not verify_password(payload.current_password, current_user.password_hash):
        raise HTTPException(status_code=401, detail="Current password is incorrect")

    if len(payload.new_password) < 8:
        raise HTTPException(status_code=400, detail="New password must be at least 8 characters")

    current_user.password_hash = hash_password(payload.new_password)
    current_user.must_change_password = False
    db.commit()
    db.refresh(current_user)
    return current_user


@router.get("/me", response_model=schemas.UserOut)
def get_me(current_user: models.User = Depends(get_current_user)):
    return current_user


@router.post("/create-member-login", response_model=schemas.UserOut, status_code=201)
def create_member_login(
    payload: schemas.CreateMemberLoginRequest,
    current_user: models.User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    member = db.query(models.Member).filter(models.Member.id == payload.member_id).first()
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")

    existing = db.query(models.User).filter(models.User.member_id == member.id).first()
    if existing:
        raise HTTPException(status_code=409, detail="This member already has a login")

    if len(payload.temporary_password) < 8:
        raise HTTPException(status_code=400, detail="Temporary password must be at least 8 characters")

    user = models.User(
        username=member.psn,
        password_hash=hash_password(payload.temporary_password),
        role=models.UserRole.MEMBER,
        member_id=member.id,
        must_change_password=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.post("/reset-member-password", response_model=schemas.UserOut)
def reset_member_password(
    payload: schemas.CreateMemberLoginRequest,
    current_user: models.User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Admin resets an existing member's password (e.g. they forgot it),
    setting must_change_password again so the next login forces a reset."""
    user = db.query(models.User).filter(models.User.member_id == payload.member_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="This member doesn't have a login yet")

    if len(payload.temporary_password) < 8:
        raise HTTPException(status_code=400, detail="Temporary password must be at least 8 characters")

    user.password_hash = hash_password(payload.temporary_password)
    user.must_change_password = True
    db.commit()
    db.refresh(user)
    return user
