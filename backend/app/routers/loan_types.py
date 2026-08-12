import uuid
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..deps import require_admin, get_current_user

router = APIRouter(prefix="/api/loan-types", tags=["loan-types"])


@router.get("", response_model=List[schemas.LoanTypeOut])
def list_loan_types(
    current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)
):
    return db.query(models.LoanType).order_by(models.LoanType.name).all()


@router.get("/{loan_type_id}", response_model=schemas.LoanTypeOut)
def get_loan_type(
    loan_type_id: uuid.UUID,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    loan_type = db.query(models.LoanType).filter(models.LoanType.id == loan_type_id).first()
    if not loan_type:
        raise HTTPException(status_code=404, detail="Loan type not found")
    return loan_type


@router.post("", response_model=schemas.LoanTypeOut, status_code=201)
def create_loan_type(
    payload: schemas.LoanTypeCreate,
    current_user: models.User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    existing = db.query(models.LoanType).filter(models.LoanType.name == payload.name).first()
    if existing:
        raise HTTPException(status_code=409, detail="A loan type with this name already exists")

    loan_type = models.LoanType(**payload.model_dump())
    db.add(loan_type)
    db.commit()
    db.refresh(loan_type)
    return loan_type


@router.put("/{loan_type_id}", response_model=schemas.LoanTypeOut)
def update_loan_type(
    loan_type_id: uuid.UUID,
    payload: schemas.LoanTypeUpdate,
    current_user: models.User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    loan_type = db.query(models.LoanType).filter(models.LoanType.id == loan_type_id).first()
    if not loan_type:
        raise HTTPException(status_code=404, detail="Loan type not found")

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(loan_type, field, value)

    db.commit()
    db.refresh(loan_type)
    return loan_type


@router.delete("/{loan_type_id}", status_code=204)
def delete_loan_type(
    loan_type_id: uuid.UUID,
    current_user: models.User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    loan_type = db.query(models.LoanType).filter(models.LoanType.id == loan_type_id).first()
    if not loan_type:
        raise HTTPException(status_code=404, detail="Loan type not found")

    # Loans reference loan_type_id without cascade delete, so block removal
    # of a type that's still in use rather than orphaning historical loans.
    in_use = db.query(models.Loan).filter(models.Loan.loan_type_id == loan_type_id).first()
    if in_use:
        raise HTTPException(
            status_code=409,
            detail="This loan type has existing loans and can't be deleted. Deactivate it instead.",
        )

    db.delete(loan_type)
    db.commit()
    return None
