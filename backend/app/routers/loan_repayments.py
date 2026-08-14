import uuid
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload

from .. import models, schemas
from ..database import get_db
from ..deps import get_current_user, require_admin, require_password_already_changed
from ..email_utils import send_email, repayment_verified_email_html, repayment_rejected_email_html

router = APIRouter(tags=["loan-repayments"])


def _assert_can_view_loan(loan: models.Loan, current_user: models.User):
    if current_user.role == models.UserRole.ADMIN:
        return
    if current_user.member_id != loan.member_id:
        raise HTTPException(status_code=403, detail="You can only act on your own loans")


@router.post(
    "/api/loans/{loan_id}/repayments",
    response_model=schemas.LoanRepaymentOut,
    status_code=201,
)
def submit_repayment(
    loan_id: uuid.UUID,
    payload: schemas.LoanRepaymentCreate,
    current_user: models.User = Depends(require_password_already_changed),
    db: Session = Depends(get_db),
):
    if current_user.role != models.UserRole.MEMBER or not current_user.member_id:
        raise HTTPException(status_code=403, detail="Only members can submit repayments")

    loan = db.query(models.Loan).filter(models.Loan.id == loan_id).first()
    if not loan:
        raise HTTPException(status_code=404, detail="Loan not found")
    if loan.member_id != current_user.member_id:
        raise HTTPException(status_code=403, detail="You can only service your own loans")
    if loan.status != models.LoanStatus.ACTIVE:
        raise HTTPException(status_code=400, detail="This loan is not active")

    if payload.amount_claimed <= 0:
        raise HTTPException(status_code=400, detail="amount_claimed must be greater than zero")

    repayment = models.LoanRepayment(
        loan_id=loan_id,
        member_id=current_user.member_id,
        amount_claimed=payload.amount_claimed,
        payment_reference=payload.payment_reference,
        receipt_image_base64=payload.receipt_image_base64,
        receipt_content_type=payload.receipt_content_type,
    )
    db.add(repayment)
    db.commit()
    db.refresh(repayment)
    return repayment


@router.get(
    "/api/loans/{loan_id}/repayments",
    response_model=List[schemas.LoanRepaymentOut],
)
def list_repayments_for_loan(
    loan_id: uuid.UUID,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    loan = db.query(models.Loan).filter(models.Loan.id == loan_id).first()
    if not loan:
        raise HTTPException(status_code=404, detail="Loan not found")
    _assert_can_view_loan(loan, current_user)

    return (
        db.query(models.LoanRepayment)
        .filter(models.LoanRepayment.loan_id == loan_id)
        .order_by(models.LoanRepayment.created_at.desc())
        .all()
    )


@router.get(
    "/api/loan-repayments",
    response_model=List[schemas.LoanRepaymentOut],
)
def list_all_repayments(
    status: Optional[models.RepaymentVerificationStatus] = None,
    current_user: models.User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Admin-only: cross-loan queue of repayments awaiting verification."""
    query = db.query(models.LoanRepayment)
    if status:
        query = query.filter(models.LoanRepayment.status == status)
    return query.order_by(models.LoanRepayment.created_at.desc()).all()


@router.get(
    "/api/loan-repayments/{repayment_id}",
    response_model=schemas.LoanRepaymentOutWithReceipt,
)
def get_repayment(
    repayment_id: uuid.UUID,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    repayment = db.query(models.LoanRepayment).filter(models.LoanRepayment.id == repayment_id).first()
    if not repayment:
        raise HTTPException(status_code=404, detail="Repayment not found")
    if current_user.role == models.UserRole.MEMBER and repayment.member_id != current_user.member_id:
        raise HTTPException(status_code=403, detail="You can only view your own repayments")
    return repayment


@router.post(
    "/api/loan-repayments/{repayment_id}/verify",
    response_model=schemas.LoanRepaymentOut,
)
def verify_repayment(
    repayment_id: uuid.UUID,
    payload: schemas.RepaymentVerificationRequest,
    current_user: models.User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    repayment = (
        db.query(models.LoanRepayment)
        .options(joinedload(models.LoanRepayment.loan).joinedload(models.Loan.member))
        .filter(models.LoanRepayment.id == repayment_id)
        .first()
    )
    if not repayment:
        raise HTTPException(status_code=404, detail="Repayment not found")
    if repayment.status != models.RepaymentVerificationStatus.AWAITING_VERIFICATION:
        raise HTTPException(status_code=400, detail="This repayment has already been reviewed")

    repayment.verified_by_user_id = current_user.id
    repayment.verified_at = datetime.utcnow()

    if payload.approved:
        repayment.status = models.RepaymentVerificationStatus.VERIFIED

        loan = repayment.loan
        loan.amount_repaid = loan.amount_repaid + repayment.amount_claimed
        if loan.amount_repaid >= loan.total_repayable:
            loan.status = models.LoanStatus.COMPLETED

        db.commit()
        db.refresh(repayment)

        send_email(
            to=loan.member.email,
            subject="Repayment received",
            html=repayment_verified_email_html(
                member_name=loan.member.name,
                loan_type_name=loan.loan_type.name if loan.loan_type else "",
                amount=repayment.amount_claimed,
                new_balance=loan.total_repayable - loan.amount_repaid,
            ),
        )
    else:
        if not payload.rejection_reason:
            raise HTTPException(status_code=400, detail="rejection_reason is required when rejecting")
        repayment.status = models.RepaymentVerificationStatus.REJECTED
        repayment.rejection_reason = payload.rejection_reason

        db.commit()
        db.refresh(repayment)

        send_email(
            to=repayment.loan.member.email,
            subject="Your repayment could not be verified",
            html=repayment_rejected_email_html(
                member_name=repayment.loan.member.name,
                loan_type_name=repayment.loan.loan_type.name if repayment.loan.loan_type else "",
                reason=payload.rejection_reason,
            ),
        )

    return repayment
