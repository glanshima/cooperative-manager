import uuid
from datetime import date, datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload

from .. import models, schemas
from ..database import get_db
from ..deps import get_current_user, require_admin, require_password_already_changed
from ..loan_calc import compute_loan_terms, compute_expected_end_date, get_effective_terms
from ..email_utils import (
    send_email,
    loan_disbursed_email_html,
    loan_rejected_email_html,
    payment_rejected_email_html,
)
from .settings import _get_or_create_settings

router = APIRouter(prefix="/api/loan-applications", tags=["loan-applications"])


def _to_detail_schema(app: models.LoanApplication) -> schemas.LoanApplicationOutWithDetails:
    return schemas.LoanApplicationOutWithDetails(
        **{
            field: getattr(app, field)
            for field in schemas.LoanApplicationOut.model_fields
        },
        member_name=app.member.name,
        member_psn=app.member.psn,
        loan_type_name=app.loan_type.name,
    )


def _to_receipt_schema(app: models.LoanApplication) -> schemas.LoanApplicationOutWithReceipt:
    return schemas.LoanApplicationOutWithReceipt(
        **_to_detail_schema(app).model_dump(),
        receipt_image_base64=app.receipt_image_base64,
    )


def _assert_can_view(app: models.LoanApplication, current_user: models.User):
    if current_user.role == models.UserRole.ADMIN:
        return
    if current_user.member_id != app.member_id:
        raise HTTPException(status_code=403, detail="You can only view your own applications")


@router.post("", response_model=schemas.LoanApplicationOutWithDetails, status_code=201)
def submit_application(
    payload: schemas.LoanApplicationCreate,
    current_user: models.User = Depends(require_password_already_changed),
    db: Session = Depends(get_db),
):
    if current_user.role != models.UserRole.MEMBER or not current_user.member_id:
        raise HTTPException(status_code=403, detail="Only members can submit loan applications")

    member = db.query(models.Member).filter(models.Member.id == current_user.member_id).first()
    if not member:
        raise HTTPException(status_code=404, detail="Member record not found")

    loan_type = (
        db.query(models.LoanType).filter(models.LoanType.id == payload.loan_type_id).first()
    )
    if not loan_type:
        raise HTTPException(status_code=404, detail="Loan type not found")
    if not loan_type.is_active:
        raise HTTPException(status_code=400, detail="This loan type is no longer active")
    if not loan_type.open_for_application:
        raise HTTPException(
            status_code=400, detail="This loan type isn't open for self-service application"
        )

    settings = _get_or_create_settings(db)

    was_restricted = False
    restriction_snapshot = None
    if member.loan_restricted:
        if settings.loan_restriction_behavior == models.LoanRestrictionBehavior.BLOCK:
            raise HTTPException(
                status_code=403,
                detail=(
                    "You currently can't apply for new loans. "
                    "Please contact the cooperative office."
                ),
            )
        # WARN: allow, but flag it for the admin reviewing this application
        was_restricted = True
        restriction_snapshot = member.restriction_reason

    # Tenure request: must not exceed the loan type's default tenure as
    # of today (equal is allowed -- effectively "no change requested").
    if payload.requested_tenure_months is not None:
        _, default_tenure_months, _ = get_effective_terms(db, loan_type, date.today())
        if payload.requested_tenure_months > default_tenure_months:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Requested tenure ({payload.requested_tenure_months} months) can't "
                    f"exceed this loan type's default tenure ({default_tenure_months} months)."
                ),
            )
        if payload.requested_tenure_months <= 0:
            raise HTTPException(status_code=400, detail="Requested tenure must be a positive number of months")

    if not payload.use_default_account and not payload.alternate_account_number:
        raise HTTPException(
            status_code=400,
            detail="Alternate account details are required when not using the default account",
        )

    application = models.LoanApplication(
        member_id=member.id,
        loan_type_id=loan_type.id,
        requested_amount=payload.requested_amount,
        requested_tenure_months=payload.requested_tenure_months,
        preferred_disbursement_date=payload.preferred_disbursement_date,
        use_default_account=payload.use_default_account,
        alternate_bank_name=payload.alternate_bank_name if not payload.use_default_account else None,
        alternate_account_name=payload.alternate_account_name if not payload.use_default_account else None,
        alternate_account_number=payload.alternate_account_number if not payload.use_default_account else None,
        member_notes=payload.member_notes,
        was_restricted_at_submission=was_restricted,
        restriction_reason_snapshot=restriction_snapshot,
        form_fee_amount=settings.loan_form_fee,
        payment_reference=payload.payment_reference,
        receipt_image_base64=payload.receipt_image_base64,
        receipt_content_type=payload.receipt_content_type,
        reapplied_from_id=payload.reapplied_from_id,
    )
    db.add(application)
    db.commit()
    db.refresh(application)

    application = (
        db.query(models.LoanApplication)
        .options(joinedload(models.LoanApplication.member), joinedload(models.LoanApplication.loan_type))
        .filter(models.LoanApplication.id == application.id)
        .first()
    )
    return _to_detail_schema(application)


@router.get("", response_model=List[schemas.LoanApplicationOutWithDetails])
def list_applications(
    status: Optional[models.LoanApplicationStatus] = None,
    payment_status: Optional[models.PaymentVerificationStatus] = None,
    undisbursed_only: bool = False,
    loan_type_id: Optional[uuid.UUID] = None,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = db.query(models.LoanApplication).options(
        joinedload(models.LoanApplication.member), joinedload(models.LoanApplication.loan_type)
    )

    if current_user.role == models.UserRole.MEMBER:
        query = query.filter(models.LoanApplication.member_id == current_user.member_id)

    if status:
        query = query.filter(models.LoanApplication.status == status)
    if payment_status:
        query = query.filter(models.LoanApplication.payment_status == payment_status)
    if undisbursed_only:
        # Convenience filter for the admin "disbursement list" view --
        # approved but not yet turned into an actual Loan.
        query = query.filter(
            models.LoanApplication.status == models.LoanApplicationStatus.APPROVED,
            models.LoanApplication.resulting_loan_id.is_(None),
        )
    if loan_type_id:
        query = query.filter(models.LoanApplication.loan_type_id == loan_type_id)

    applications = query.order_by(models.LoanApplication.created_at.desc()).all()
    return [_to_detail_schema(a) for a in applications]


@router.get("/{application_id}", response_model=schemas.LoanApplicationOutWithReceipt)
def get_application(
    application_id: uuid.UUID,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    application = (
        db.query(models.LoanApplication)
        .options(joinedload(models.LoanApplication.member), joinedload(models.LoanApplication.loan_type))
        .filter(models.LoanApplication.id == application_id)
        .first()
    )
    if not application:
        raise HTTPException(status_code=404, detail="Application not found")

    _assert_can_view(application, current_user)
    return _to_receipt_schema(application)


@router.post("/{application_id}/verify-payment", response_model=schemas.LoanApplicationOutWithDetails)
def verify_payment(
    application_id: uuid.UUID,
    payload: schemas.PaymentVerificationRequest,
    current_user: models.User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    application = (
        db.query(models.LoanApplication)
        .options(joinedload(models.LoanApplication.member), joinedload(models.LoanApplication.loan_type))
        .filter(models.LoanApplication.id == application_id)
        .first()
    )
    if not application:
        raise HTTPException(status_code=404, detail="Application not found")

    if application.payment_status != models.PaymentVerificationStatus.AWAITING_VERIFICATION:
        raise HTTPException(status_code=400, detail="This payment has already been reviewed")

    application.payment_verified_by_user_id = current_user.id
    application.payment_verified_at = datetime.utcnow()

    if payload.approved:
        application.payment_status = models.PaymentVerificationStatus.VERIFIED
    else:
        if not payload.rejection_reason:
            raise HTTPException(status_code=400, detail="rejection_reason is required when rejecting a payment")
        application.payment_status = models.PaymentVerificationStatus.REJECTED
        application.payment_rejection_reason = payload.rejection_reason
        # An invalid payment means the application itself can't proceed
        application.status = models.LoanApplicationStatus.REJECTED
        application.admin_notes = f"Payment not verified: {payload.rejection_reason}"

        send_email(
            to=application.member.email,
            subject="Your loan form payment could not be verified",
            html=payment_rejected_email_html(
                member_name=application.member.name,
                loan_type_name=application.loan_type.name,
                reason=payload.rejection_reason,
            ),
        )

    db.commit()
    db.refresh(application)
    return _to_detail_schema(application)


@router.post("/{application_id}/decide", response_model=schemas.LoanApplicationOutWithDetails)
def decide_application(
    application_id: uuid.UUID,
    payload: schemas.LoanDecisionRequest,
    current_user: models.User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Records the approve/reject decision only -- does NOT create a Loan
    or send any email. Approving just makes the application eligible for
    a separate, explicit disbursement step (see /disburse below), so a
    member never sees a loan as "active" before money has actually moved.
    Rejection still emails the member, since that's a terminal outcome
    they need to know about; approval doesn't email because the member
    already sees the approved status on their dashboard, and the
    meaningful notification happens at actual disbursement."""
    application = (
        db.query(models.LoanApplication)
        .options(joinedload(models.LoanApplication.member), joinedload(models.LoanApplication.loan_type))
        .filter(models.LoanApplication.id == application_id)
        .first()
    )
    if not application:
        raise HTTPException(status_code=404, detail="Application not found")

    if application.payment_status != models.PaymentVerificationStatus.VERIFIED:
        raise HTTPException(
            status_code=400,
            detail="This application's loan-form payment must be verified before a decision can be made",
        )
    if application.status != models.LoanApplicationStatus.PENDING:
        raise HTTPException(status_code=400, detail="This application has already been decided")

    application.reviewed_by_user_id = current_user.id
    application.reviewed_at = datetime.utcnow()
    application.admin_notes = payload.admin_notes

    if payload.approved:
        if not payload.approved_amount or payload.approved_amount <= 0:
            raise HTTPException(status_code=400, detail="approved_amount is required when approving")
        if not payload.approved_tenure_months or payload.approved_tenure_months <= 0:
            raise HTTPException(status_code=400, detail="approved_tenure_months is required when approving")

        # Flag if the admin didn't simply grant what was requested, so the
        # reason is expected (not strictly enforced -- an admin might have
        # an obvious reason that doesn't need restating).
        application.approved_amount = payload.approved_amount
        application.approved_tenure_months = payload.approved_tenure_months
        application.tenure_decision_reason = payload.tenure_decision_reason
        application.status = models.LoanApplicationStatus.APPROVED
        # resulting_loan_id stays null -- set only by /disburse below

        db.commit()
        db.refresh(application)
    else:
        application.status = models.LoanApplicationStatus.REJECTED
        application.can_reapply = payload.can_reapply
        db.commit()
        db.refresh(application)

        send_email(
            to=application.member.email,
            subject="Update on your loan application",
            html=loan_rejected_email_html(
                member_name=application.member.name,
                loan_type_name=application.loan_type.name,
                requested_amount=application.requested_amount,
                admin_notes=payload.admin_notes or "",
            ),
        )

    return _to_detail_schema(application)


@router.post("/{application_id}/disburse", response_model=schemas.LoanApplicationOutWithDetails)
def disburse_application(
    application_id: uuid.UUID,
    payload: schemas.DisburseRequest = schemas.DisburseRequest(),
    current_user: models.User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Actually creates the Loan and moves it to ACTIVE. This is the
    moment a loan really "starts" -- disbursement_date is always
    normalized to the 1st of the current month, regardless of the
    member's preferred_disbursement_date (which is only ever a
    preference). The interest rate/flat_charge used are whichever were
    effective as of this disbursement date (see LoanTypeRateVersion);
    the tenure is fixed to whatever was approved at decision time. Sends
    the one detailed email covering everything the member needs.

    Balance deduction: if the admin selects existing active loan(s) of
    this member (via deduct_loan_ids or deduct_all_active), those loans
    are FULLY closed out (amount_repaid = total_repayable, status ->
    COMPLETED -- no partial deduction) and their combined outstanding
    balance is subtracted from what the member actually receives on this
    new loan. The new loan's own principal/interest/total_repayable are
    unaffected by this -- only net_disbursed (the payout) shrinks. If the
    deducted total would make net_disbursed negative, the disbursement is
    rejected with a clear error rather than silently going negative --
    an admin should resolve that manually (e.g. deduct fewer loans, or
    handle the shortfall outside the system) rather than have the app
    guess what to do.
    """
    application = (
        db.query(models.LoanApplication)
        .options(joinedload(models.LoanApplication.member), joinedload(models.LoanApplication.loan_type))
        .filter(models.LoanApplication.id == application_id)
        .first()
    )
    if not application:
        raise HTTPException(status_code=404, detail="Application not found")

    if application.status != models.LoanApplicationStatus.APPROVED:
        raise HTTPException(status_code=400, detail="Only approved applications can be disbursed")
    if application.resulting_loan_id:
        raise HTTPException(status_code=400, detail="This application has already been disbursed")

    loan_type = application.loan_type
    disbursement_date = date.today().replace(day=1)

    interest_rate, _default_tenure, flat_charge = get_effective_terms(db, loan_type, disbursement_date)
    interest_amount, net_disbursed, total_repayable, monthly_installment = compute_loan_terms(
        application.approved_amount, interest_rate, flat_charge, application.approved_tenure_months
    )
    expected_end_date = compute_expected_end_date(disbursement_date, application.approved_tenure_months)

    if application.use_default_account:
        disbursement_bank_name = application.member.bank_name
        disbursement_account_name = application.member.name
        disbursement_account_number = application.member.account_number
    else:
        disbursement_bank_name = application.alternate_bank_name
        disbursement_account_name = application.alternate_account_name
        disbursement_account_number = application.alternate_account_number

    # --- Balance deduction (Round 2 feature) ---
    active_loans_query = db.query(models.Loan).filter(
        models.Loan.member_id == application.member_id,
        models.Loan.status == models.LoanStatus.ACTIVE,
    )
    loans_to_deduct = []
    if payload.deduct_all_active:
        loans_to_deduct = active_loans_query.all()
    elif payload.deduct_loan_ids:
        loans_to_deduct = active_loans_query.filter(models.Loan.id.in_(payload.deduct_loan_ids)).all()
        found_ids = {loan.id for loan in loans_to_deduct}
        missing = set(payload.deduct_loan_ids) - found_ids
        if missing:
            raise HTTPException(
                status_code=400,
                detail=f"These loan IDs are not this member's active loans: {missing}",
            )

    total_deducted = sum((loan.total_repayable - loan.amount_repaid) for loan in loans_to_deduct)
    if total_deducted > net_disbursed:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Selected loans total {total_deducted} outstanding, which exceeds this loan's "
                f"net disbursed amount of {net_disbursed}. Deduct fewer loans, or handle the "
                f"shortfall outside the system."
            ),
        )

    loan = models.Loan(
        member_id=application.member_id,
        loan_type_id=loan_type.id,
        principal=application.approved_amount,
        interest_amount=interest_amount,
        net_disbursed=net_disbursed - total_deducted,
        total_repayable=total_repayable,
        monthly_installment=monthly_installment,
        disbursement_date=disbursement_date,
        expected_end_date=expected_end_date,
        disbursement_bank_name=disbursement_bank_name,
        disbursement_account_name=disbursement_account_name,
        disbursement_account_number=disbursement_account_number,
        amount_repaid=0,
        status=models.LoanStatus.ACTIVE,
        notes=f"Disbursed from application {application.id}",
    )
    db.add(loan)
    db.flush()  # get loan.id without a full commit yet

    for old_loan in loans_to_deduct:
        old_loan.amount_repaid = old_loan.total_repayable
        old_loan.status = models.LoanStatus.COMPLETED
        old_loan.notes = (
            (old_loan.notes + " " if old_loan.notes else "")
            + f"Closed out via offset against new loan {loan.id} disbursed {disbursement_date}."
        )

    application.resulting_loan_id = loan.id

    db.commit()
    db.refresh(application)

    send_email(
        to=application.member.email,
        subject="Your loan has been disbursed",
        html=loan_disbursed_email_html(
            member_name=application.member.name,
            loan_type_name=loan_type.name,
            approved_amount=application.approved_amount,
            interest_amount=interest_amount,
            net_disbursed=net_disbursed - total_deducted,
            total_repayable=total_repayable,
            monthly_installment=monthly_installment,
            tenure_months=application.approved_tenure_months,
            disbursement_date=disbursement_date,
            expected_end_date=expected_end_date,
            disbursement_bank_name=disbursement_bank_name,
            disbursement_account_name=disbursement_account_name,
            disbursement_account_number=disbursement_account_number,
            deducted_amount=total_deducted if total_deducted else None,
        ),
    )

    return _to_detail_schema(application)


@router.post("/{application_id}/cancel", response_model=schemas.LoanApplicationOutWithDetails)
def cancel_application(
    application_id: uuid.UUID,
    current_user: models.User = Depends(require_password_already_changed),
    db: Session = Depends(get_db),
):
    """Member cancels their own application before it's disbursed. The
    loan-form fee is NOT refunded -- cancelling is a deliberate choice
    with that tradeoff; the frontend should warn about this and suggest
    /reschedule instead if the member just wants a different date."""
    if current_user.role != models.UserRole.MEMBER or not current_user.member_id:
        raise HTTPException(status_code=403, detail="Only members can cancel their own applications")

    application = (
        db.query(models.LoanApplication)
        .options(joinedload(models.LoanApplication.member), joinedload(models.LoanApplication.loan_type))
        .filter(models.LoanApplication.id == application_id)
        .first()
    )
    if not application:
        raise HTTPException(status_code=404, detail="Application not found")
    if application.member_id != current_user.member_id:
        raise HTTPException(status_code=403, detail="You can only cancel your own applications")

    cancellable = application.status == models.LoanApplicationStatus.PENDING or (
        application.status == models.LoanApplicationStatus.APPROVED and not application.resulting_loan_id
    )
    if not cancellable:
        raise HTTPException(
            status_code=400,
            detail="This application can no longer be cancelled (already disbursed, rejected, or cancelled).",
        )

    application.status = models.LoanApplicationStatus.CANCELLED
    application.cancelled_at = datetime.utcnow()
    db.commit()
    db.refresh(application)
    return _to_detail_schema(application)


@router.post("/{application_id}/reschedule", response_model=schemas.LoanApplicationOutWithDetails)
def reschedule_application(
    application_id: uuid.UUID,
    payload: schemas.RescheduleRequest,
    current_user: models.User = Depends(require_password_already_changed),
    db: Session = Depends(get_db),
):
    """Member updates their preferred disbursement date WITHOUT
    cancelling -- no fee impact at all, since the application itself
    isn't ending. Same eligibility window as /cancel."""
    if current_user.role != models.UserRole.MEMBER or not current_user.member_id:
        raise HTTPException(status_code=403, detail="Only members can reschedule their own applications")

    application = (
        db.query(models.LoanApplication)
        .options(joinedload(models.LoanApplication.member), joinedload(models.LoanApplication.loan_type))
        .filter(models.LoanApplication.id == application_id)
        .first()
    )
    if not application:
        raise HTTPException(status_code=404, detail="Application not found")
    if application.member_id != current_user.member_id:
        raise HTTPException(status_code=403, detail="You can only reschedule your own applications")

    reschedulable = application.status == models.LoanApplicationStatus.PENDING or (
        application.status == models.LoanApplicationStatus.APPROVED and not application.resulting_loan_id
    )
    if not reschedulable:
        raise HTTPException(
            status_code=400,
            detail="This application can no longer be rescheduled (already disbursed, rejected, or cancelled).",
        )

    application.preferred_disbursement_date = payload.preferred_disbursement_date
    db.commit()
    db.refresh(application)
    return _to_detail_schema(application)


@router.post("/{application_id}/reapply", response_model=schemas.LoanApplicationOutWithDetails, status_code=201)
def reapply(
    application_id: uuid.UUID,
    payload: schemas.ReapplyRequest,
    current_user: models.User = Depends(require_password_already_changed),
    db: Session = Depends(get_db),
):
    """Creates a brand new LoanApplication referencing a rejected one.
    Always requires fresh payment proof -- the original payment was
    already consumed by the application it was submitted with. Blocked
    if the admin marked the original as can_reapply=False (genuine
    non-qualification, not a fixable mistake)."""
    if current_user.role != models.UserRole.MEMBER or not current_user.member_id:
        raise HTTPException(status_code=403, detail="Only members can reapply")

    original = (
        db.query(models.LoanApplication)
        .filter(models.LoanApplication.id == application_id)
        .first()
    )
    if not original:
        raise HTTPException(status_code=404, detail="Original application not found")
    if original.member_id != current_user.member_id:
        raise HTTPException(status_code=403, detail="You can only reapply from your own applications")
    if original.status != models.LoanApplicationStatus.REJECTED:
        raise HTTPException(status_code=400, detail="Only rejected applications can be reapplied from")
    if not original.can_reapply:
        raise HTTPException(
            status_code=403,
            detail="This application isn't eligible for reapplication. Please contact the cooperative office.",
        )

    create_payload = schemas.LoanApplicationCreate(
        loan_type_id=original.loan_type_id,
        requested_amount=payload.requested_amount or original.requested_amount,
        requested_tenure_months=payload.requested_tenure_months
        if payload.requested_tenure_months is not None
        else original.requested_tenure_months,
        preferred_disbursement_date=payload.preferred_disbursement_date,
        use_default_account=payload.use_default_account,
        alternate_bank_name=payload.alternate_bank_name,
        alternate_account_name=payload.alternate_account_name,
        alternate_account_number=payload.alternate_account_number,
        member_notes=payload.member_notes,
        payment_reference=payload.payment_reference,
        receipt_image_base64=payload.receipt_image_base64,
        receipt_content_type=payload.receipt_content_type,
        reapplied_from_id=original.id,
    )
    return submit_application(create_payload, current_user, db)
