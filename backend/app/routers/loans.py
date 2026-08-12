import uuid
from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload

from .. import models, schemas
from ..database import get_db
from ..deps import require_admin, get_current_user
from ..loan_calc import compute_loan_terms, compute_expected_end_date

router = APIRouter(prefix="/api/loans", tags=["loans"])


def _to_detail_schema(loan: models.Loan) -> schemas.LoanOutWithDetails:
    """Attach member/loan-type names and computed balance for list views."""
    return schemas.LoanOutWithDetails(
        id=loan.id,
        member_id=loan.member_id,
        loan_type_id=loan.loan_type_id,
        principal=loan.principal,
        interest_amount=loan.interest_amount,
        total_repayable=loan.total_repayable,
        monthly_installment=loan.monthly_installment,
        disbursement_date=loan.disbursement_date,
        expected_end_date=loan.expected_end_date,
        amount_repaid=loan.amount_repaid,
        status=loan.status,
        notes=loan.notes,
        created_at=loan.created_at,
        updated_at=loan.updated_at,
        member_name=loan.member.name,
        member_psn=loan.member.psn,
        loan_type_name=loan.loan_type.name,
        balance=loan.total_repayable - loan.amount_repaid,
    )


@router.get("", response_model=List[schemas.LoanOutWithDetails])
def list_loans(
    member_id: Optional[uuid.UUID] = None,
    status: Optional[models.LoanStatus] = None,
    skip: int = 0,
    limit: int = 100,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = db.query(models.Loan).options(
        joinedload(models.Loan.member), joinedload(models.Loan.loan_type)
    )

    # Members can only see their own loans; admins see everything.
    if current_user.role == models.UserRole.MEMBER:
        query = query.filter(models.Loan.member_id == current_user.member_id)
    elif member_id:
        query = query.filter(models.Loan.member_id == member_id)

    if status:
        query = query.filter(models.Loan.status == status)

    loans = (
        query.order_by(models.Loan.disbursement_date.desc()).offset(skip).limit(limit).all()
    )
    return [_to_detail_schema(loan) for loan in loans]


@router.get("/{loan_id}", response_model=schemas.LoanOutWithDetails)
def get_loan(
    loan_id: uuid.UUID,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    loan = (
        db.query(models.Loan)
        .options(joinedload(models.Loan.member), joinedload(models.Loan.loan_type))
        .filter(models.Loan.id == loan_id)
        .first()
    )
    if not loan:
        raise HTTPException(status_code=404, detail="Loan not found")
    if current_user.role == models.UserRole.MEMBER and loan.member_id != current_user.member_id:
        raise HTTPException(status_code=403, detail="You can only view your own loans")
    return _to_detail_schema(loan)


@router.post("", response_model=schemas.LoanOutWithDetails, status_code=201)
def create_loan(
    payload: schemas.LoanCreate,
    current_user: models.User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    member = db.query(models.Member).filter(models.Member.id == payload.member_id).first()
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")

    loan_type = (
        db.query(models.LoanType).filter(models.LoanType.id == payload.loan_type_id).first()
    )
    if not loan_type:
        raise HTTPException(status_code=404, detail="Loan type not found")
    if not loan_type.is_active:
        raise HTTPException(status_code=400, detail="This loan type is no longer active")

    # --- Core disbursement calculation, mirrors the spreadsheet's IFS formulas ---
    # (see app/loan_calc.py -- shared with application-approval disbursement)
    interest_amount, total_repayable, monthly_installment = compute_loan_terms(
        payload.principal, loan_type.interest_rate, loan_type.flat_charge, loan_type.tenure_months
    )
    expected_end_date = compute_expected_end_date(payload.disbursement_date, loan_type.tenure_months)

    loan = models.Loan(
        member_id=payload.member_id,
        loan_type_id=payload.loan_type_id,
        principal=payload.principal,
        interest_amount=interest_amount,
        total_repayable=total_repayable,
        monthly_installment=monthly_installment,
        disbursement_date=payload.disbursement_date,
        expected_end_date=expected_end_date,
        amount_repaid=0,
        status=models.LoanStatus.ACTIVE,
        notes=payload.notes,
    )
    db.add(loan)
    db.commit()
    db.refresh(loan)

    loan = (
        db.query(models.Loan)
        .options(joinedload(models.Loan.member), joinedload(models.Loan.loan_type))
        .filter(models.Loan.id == loan.id)
        .first()
    )
    return _to_detail_schema(loan)


@router.put("/{loan_id}", response_model=schemas.LoanOutWithDetails)
def update_loan(
    loan_id: uuid.UUID,
    payload: schemas.LoanUpdate,
    current_user: models.User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    loan = db.query(models.Loan).filter(models.Loan.id == loan_id).first()
    if not loan:
        raise HTTPException(status_code=404, detail="Loan not found")

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(loan, field, value)

    # Auto-complete a loan once it's fully repaid, unless the caller
    # explicitly set a different status in this same request.
    if "status" not in payload.model_dump(exclude_unset=True):
        if loan.amount_repaid >= loan.total_repayable:
            loan.status = models.LoanStatus.COMPLETED

    db.commit()
    db.refresh(loan)

    loan = (
        db.query(models.Loan)
        .options(joinedload(models.Loan.member), joinedload(models.Loan.loan_type))
        .filter(models.Loan.id == loan.id)
        .first()
    )
    return _to_detail_schema(loan)


@router.delete("/{loan_id}", status_code=204)
def delete_loan(
    loan_id: uuid.UUID,
    current_user: models.User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    loan = db.query(models.Loan).filter(models.Loan.id == loan_id).first()
    if not loan:
        raise HTTPException(status_code=404, detail="Loan not found")

    db.delete(loan)
    db.commit()
    return None


@router.get("/member/{member_id}/balance", response_model=dict)
def get_member_loan_balance(
    member_id: uuid.UUID,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Running total across all of a member's active loans - the
    replacement for the spreadsheet's hardcoded loan_liabilities_helper_table
    cell-chain formulas."""
    if current_user.role == models.UserRole.MEMBER and member_id != current_user.member_id:
        raise HTTPException(status_code=403, detail="You can only view your own balance")

    loans = (
        db.query(models.Loan)
        .filter(models.Loan.member_id == member_id, models.Loan.status == models.LoanStatus.ACTIVE)
        .all()
    )
    total_outstanding = sum((loan.total_repayable - loan.amount_repaid) for loan in loans)
    return {
        "member_id": str(member_id),
        "active_loan_count": len(loans),
        "total_outstanding_balance": total_outstanding,
    }
