import uuid
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session, joinedload

from .. import models, schemas, audit_service, notification_service
from ..database import get_db
from ..deps import (
    get_current_user,
    require_module_enabled,
    require_password_already_changed,
    require_permission,
    user_has_permission,
)
from ..idempotency import IdempotencyContext, idempotency_check
from ..self_conflict import (
    get_conflicted_member_ids,
    log_conflicted_view,
    mark_conflicted_reads,
    require_no_member_conflict,
)

router = APIRouter(
    tags=["loan-fees"],
    dependencies=[Depends(require_module_enabled("loans"))],
)


def _to_details_schema(payment: models.LoanFeePayment) -> schemas.LoanFeePaymentOutWithDetails:
    return schemas.LoanFeePaymentOutWithDetails(
        **schemas.LoanFeePaymentOut.model_validate(payment).model_dump(),
        member_name=payment.member.name if payment.member else "",
        member_psn=payment.member.psn if payment.member else "",
        loan_type_name=(
            payment.loan.loan_type.name if payment.loan and payment.loan.loan_type else ""
        ),
    )


@router.post(
    "/api/loans/{loan_id}/fee-payment",
    response_model=schemas.LoanFeePaymentOut,
    status_code=201,
)
def submit_fee_payment(
    loan_id: uuid.UUID,
    payload: schemas.LoanFeePaymentCreate,
    current_user: models.User = Depends(require_password_already_changed),
    db: Session = Depends(get_db),
):
    """The member confirms they have paid the loan's processing fee. The
    amount is the snapshot on the loan -- never client-supplied -- because
    this ledger is cooperative income, not a negotiation."""
    if current_user.role != models.UserRole.MEMBER or not current_user.member_id:
        raise HTTPException(status_code=403, detail="Only members can submit fee payments")

    loan = db.query(models.Loan).filter(models.Loan.id == loan_id).first()
    if not loan:
        raise HTTPException(status_code=404, detail="Loan not found")
    if loan.member_id != current_user.member_id:
        raise HTTPException(status_code=403, detail="You can only pay fees on your own loans")
    if not loan.fee_amount or loan.fee_amount <= 0:
        raise HTTPException(status_code=400, detail="This loan has no fee to pay")

    existing = db.query(models.LoanFeePayment).filter(models.LoanFeePayment.loan_id == loan_id).all()
    if any(p.status == models.FeePaymentStatus.VERIFIED for p in existing):
        raise HTTPException(status_code=400, detail="This loan's fee has already been paid")
    if any(p.status == models.FeePaymentStatus.AWAITING_VERIFICATION for p in existing):
        raise HTTPException(status_code=400, detail="A fee payment for this loan is already awaiting review")

    payment = models.LoanFeePayment(
        loan_id=loan.id,
        member_id=loan.member_id,
        amount=loan.fee_amount,
        payment_reference=payload.payment_reference,
        receipt_image_base64=payload.receipt_image_base64,
        receipt_content_type=payload.receipt_content_type,
    )
    db.add(payment)
    notification_service.notify_staff(
        db,
        permission_code="loan.fee_verify",
        category=models.NotificationCategory.LOAN,
        title="Loan fee payment submitted",
        body=(
            f"{loan.member.name} submitted proof of payment of {loan.fee_amount} "
            f"for the {loan.loan_type.name if loan.loan_type else 'loan'} fee."
        ),
        link_path="/admin/loan-fees",
    )
    db.commit()
    db.refresh(payment)
    return payment


@router.get(
    "/api/loans/{loan_id}/fee-payments",
    response_model=List[schemas.LoanFeePaymentOut],
)
def list_fee_payments_for_loan(
    loan_id: uuid.UUID,
    request: Request,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    loan = db.query(models.Loan).filter(models.Loan.id == loan_id).first()
    if not loan:
        raise HTTPException(status_code=404, detail="Loan not found")
    if current_user.role == models.UserRole.MEMBER:
        if current_user.member_id != loan.member_id:
            raise HTTPException(status_code=403, detail="You can only view your own loan's fees")
    elif not user_has_permission(db, current_user, "loan.view"):
        raise HTTPException(status_code=403, detail="You do not have the 'loan.view' permission")

    payments = (
        db.query(models.LoanFeePayment)
        .filter(models.LoanFeePayment.loan_id == loan_id)
        .order_by(models.LoanFeePayment.created_at.desc())
        .all()
    )
    items = [schemas.LoanFeePaymentOut.model_validate(p) for p in payments]
    flagged = mark_conflicted_reads(items, get_conflicted_member_ids(db, current_user))
    log_conflicted_view(
        db,
        current_user,
        conflicted_count=flagged,
        action_description="viewed a loan's fee payments",
        entity_type="loan_fee_payment",
        entity_id=str(loan_id),
        request=request,
    )
    return items


@router.get(
    "/api/loan-fees",
    response_model=List[schemas.LoanFeePaymentOutWithDetails],
)
def list_all_fee_payments(
    request: Request,
    status: Optional[models.FeePaymentStatus] = None,
    current_user: models.User = Depends(require_permission("loan.view")),
    db: Session = Depends(get_db),
):
    """Cross-loan review queue. The frontend requests
    ?status=awaiting_verification for the queue and no filter for history."""
    query = db.query(models.LoanFeePayment).options(
        joinedload(models.LoanFeePayment.loan).joinedload(models.Loan.member),
        joinedload(models.LoanFeePayment.loan).joinedload(models.Loan.loan_type),
        joinedload(models.LoanFeePayment.member),
    )
    if status:
        query = query.filter(models.LoanFeePayment.status == status)
    payments = query.order_by(models.LoanFeePayment.created_at.desc()).all()

    items = [_to_details_schema(payment) for payment in payments]
    flagged = mark_conflicted_reads(items, get_conflicted_member_ids(db, current_user))
    log_conflicted_view(
        db,
        current_user,
        conflicted_count=flagged,
        action_description="browsed the loan fee queue",
        entity_type="loan_fee_payment",
        request=request,
    )
    return items


@router.get(
    "/api/loan-fees/{payment_id}",
    response_model=schemas.LoanFeePaymentOutWithDetails,
)
def get_fee_payment(
    payment_id: uuid.UUID,
    request: Request,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    payment = (
        db.query(models.LoanFeePayment)
        .options(
            joinedload(models.LoanFeePayment.loan).joinedload(models.Loan.member),
            joinedload(models.LoanFeePayment.loan).joinedload(models.Loan.loan_type),
            joinedload(models.LoanFeePayment.member),
        )
        .filter(models.LoanFeePayment.id == payment_id)
        .first()
    )
    if not payment:
        raise HTTPException(status_code=404, detail="Fee payment not found")
    if current_user.role == models.UserRole.MEMBER:
        if current_user.member_id != payment.member_id:
            raise HTTPException(status_code=403, detail="You can only view your own fee payments")
    elif not user_has_permission(db, current_user, "loan.view"):
        raise HTTPException(status_code=403, detail="You do not have the 'loan.view' permission")

    conflicted = payment.member_id in get_conflicted_member_ids(db, current_user)
    if conflicted:
        log_conflicted_view(
            db,
            current_user,
            conflicted_count=1,
            action_description="viewed a loan fee payment",
            entity_type="loan_fee_payment",
            entity_id=str(payment.id),
            request=request,
        )
    item = _to_details_schema(payment)
    item.conflicted = conflicted
    return item


@router.get(
    "/api/loan-fees/{payment_id}/receipt",
    response_model=schemas.LoanFeePaymentOutWithReceipt,
)
def get_fee_payment_receipt(
    payment_id: uuid.UUID,
    request: Request,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    payment = db.query(models.LoanFeePayment).filter(models.LoanFeePayment.id == payment_id).first()
    if not payment:
        raise HTTPException(status_code=404, detail="Fee payment not found")
    if current_user.role == models.UserRole.MEMBER:
        if current_user.member_id != payment.member_id:
            raise HTTPException(status_code=403, detail="You can only view your own fee payments")
    elif not user_has_permission(db, current_user, "loan.view"):
        raise HTTPException(status_code=403, detail="You do not have the 'loan.view' permission")

    conflicted = payment.member_id in get_conflicted_member_ids(db, current_user)
    if conflicted:
        log_conflicted_view(
            db,
            current_user,
            conflicted_count=1,
            action_description="viewed a loan fee payment receipt",
            entity_type="loan_fee_payment",
            entity_id=str(payment.id),
            request=request,
        )
    item = schemas.LoanFeePaymentOutWithReceipt.model_validate(payment)
    item.conflicted = conflicted
    return item


@router.post(
    "/api/loan-fees/{payment_id}/verify",
    response_model=schemas.LoanFeePaymentOut,
)
def verify_fee_payment(
    payment_id: uuid.UUID,
    payload: schemas.FeePaymentVerificationRequest,
    request: Request,
    current_user: models.User = Depends(require_permission("loan.fee_verify")),
    db: Session = Depends(get_db),
    idem: IdempotencyContext = Depends(idempotency_check),
):
    """Recognition of cooperative income: a verified row is the record the
    cashbook will report. It deliberately touches nothing on the loan --
    the fee was never part of the payout or the repayment."""
    if idem.cached_response is not None:
        return idem.cached_response

    payment = (
        db.query(models.LoanFeePayment)
        .options(joinedload(models.LoanFeePayment.loan).joinedload(models.Loan.member))
        .filter(models.LoanFeePayment.id == payment_id)
        .with_for_update(of=models.LoanFeePayment)
        .first()
    )
    if not payment:
        raise HTTPException(status_code=404, detail="Fee payment not found")

    require_no_member_conflict(
        db,
        current_user,
        payment,
        action_description="verify this loan fee payment",
        permission_code="loan.fee_verify",
        entity_type="loan_fee_payment",
        entity_id=str(payment.id),
        request=request,
    )

    if payment.status != models.FeePaymentStatus.AWAITING_VERIFICATION:
        raise HTTPException(status_code=400, detail="This fee payment has already been reviewed")

    payment.verified_by_user_id = current_user.id
    payment.verified_at = datetime.utcnow()

    if payload.approved:
        payment.status = models.FeePaymentStatus.VERIFIED
        notification_service.notify_member(
            db,
            payment.member,
            category=models.NotificationCategory.LOAN,
            title="Loan fee payment verified",
            body=(
                f"Your loan fee payment of {payment.amount} was verified. "
                "The fee is settled and does not affect your loan balance."
            ),
            link_path="/dashboard",
        )
        db.commit()
        db.refresh(payment)
        audit_service.log_event(
            db,
            actor=current_user,
            event_type="loan_fee.verified",
            action="approve",
            entity_type="loan_fee_payment",
            entity_id=str(payment.id),
            new_values={"amount": str(payment.amount), "loan_id": str(payment.loan_id)},
            request=request,
        )
    else:
        if not payload.rejection_reason:
            raise HTTPException(status_code=400, detail="rejection_reason is required when rejecting")
        payment.status = models.FeePaymentStatus.REJECTED
        payment.rejection_reason = payload.rejection_reason
        notification_service.notify_member(
            db,
            payment.member,
            category=models.NotificationCategory.LOAN,
            title="Loan fee payment not verified",
            body=f"Your loan fee payment could not be verified: {payload.rejection_reason}",
            link_path="/dashboard",
        )
        db.commit()
        db.refresh(payment)
        audit_service.log_event(
            db,
            actor=current_user,
            event_type="loan_fee.rejected",
            action="reject",
            entity_type="loan_fee_payment",
            entity_id=str(payment.id),
            reason=payload.rejection_reason,
            request=request,
        )

    result = schemas.LoanFeePaymentOut.model_validate(payment)
    idem.store(result.model_dump(mode="json"))
    return payment
