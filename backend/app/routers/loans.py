import uuid
from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session, joinedload

from .. import models, schemas, audit_service
from ..database import get_db
from ..deps import require_admin, get_current_user, require_permission, user_has_permission
from ..loan_calc import compute_loan_terms, compute_expected_end_date, get_effective_terms
from ..self_conflict import require_no_self_conflict

router = APIRouter(prefix="/api/loans", tags=["loans"])


def _to_detail_schema(loan: models.Loan) -> schemas.LoanOutWithDetails:
    """Attach member/loan-type names and computed balance for list views."""
    return schemas.LoanOutWithDetails(
        id=loan.id,
        member_id=loan.member_id,
        loan_type_id=loan.loan_type_id,
        principal=loan.principal,
        interest_amount=loan.interest_amount,
        net_disbursed=loan.net_disbursed,
        total_repayable=loan.total_repayable,
        monthly_installment=loan.monthly_installment,
        disbursement_date=loan.disbursement_date,
        expected_end_date=loan.expected_end_date,
        disbursement_bank_name=loan.disbursement_bank_name,
        disbursement_account_name=loan.disbursement_account_name,
        disbursement_account_number=loan.disbursement_account_number,
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

    # Members can only see their own loans; admins need loan.view.
    if current_user.role == models.UserRole.MEMBER:
        query = query.filter(models.Loan.member_id == current_user.member_id)
    else:
        if not user_has_permission(db, current_user, "loan.view"):
            raise HTTPException(status_code=403, detail="You do not have the 'loan.view' permission")
        if member_id:
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
    if current_user.role == models.UserRole.MEMBER:
        if loan.member_id != current_user.member_id:
            raise HTTPException(status_code=403, detail="You can only view your own loans")
    elif not user_has_permission(db, current_user, "loan.view"):
        raise HTTPException(status_code=403, detail="You do not have the 'loan.view' permission")
    return _to_detail_schema(loan)


@router.post("", response_model=schemas.LoanOutWithDetails, status_code=201)
def create_loan(
    payload: schemas.LoanCreate,
    request: Request,
    current_user: models.User = Depends(require_permission("disbursement.submit")),
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
    # Direct admin disbursement uses the rate effective as of the chosen
    # disbursement_date, and the loan type's default tenure (there's no
    # "requested tenure" negotiation on this admin-direct path).
    interest_rate, tenure_months, flat_charge = get_effective_terms(
        db, loan_type, payload.disbursement_date
    )
    interest_amount, net_disbursed, total_repayable, monthly_installment = compute_loan_terms(
        payload.principal, interest_rate, flat_charge, tenure_months
    )
    expected_end_date = compute_expected_end_date(payload.disbursement_date, tenure_months)

    loan = models.Loan(
        member_id=payload.member_id,
        loan_type_id=payload.loan_type_id,
        principal=payload.principal,
        interest_amount=interest_amount,
        net_disbursed=net_disbursed,
        total_repayable=total_repayable,
        monthly_installment=monthly_installment,
        disbursement_date=payload.disbursement_date,
        expected_end_date=expected_end_date,
        disbursement_bank_name=member.bank_name,
        disbursement_account_name=member.name,
        disbursement_account_number=member.account_number,
        amount_repaid=0,
        status=models.LoanStatus.ACTIVE,
        notes=payload.notes,
    )
    db.add(loan)
    db.commit()
    db.refresh(loan)

    audit_service.log_event(
        db,
        actor=current_user,
        event_type="loan.created_direct",
        action="create",
        entity_type="loan",
        entity_id=str(loan.id),
        new_values={"member_id": str(loan.member_id), "principal": str(loan.principal)},
        reason="Created via direct admin disbursement (no loan_application)",
        request=request,
    )

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
    request: Request,
    current_user: models.User = Depends(require_permission("accounting.adjust")),
    db: Session = Depends(get_db),
):
    loan = db.query(models.Loan).filter(models.Loan.id == loan_id).first()
    if not loan:
        raise HTTPException(status_code=404, detail="Loan not found")

    require_no_self_conflict(
        db,
        current_user,
        loan,
        action_description="adjust your own loan",
        permission_code="accounting.adjust",
        entity_type="loan",
        entity_id=str(loan.id),
        request=request,
    )

    changes = payload.model_dump(exclude_unset=True)
    previous = {field: getattr(loan, field) for field in changes}
    for field, value in changes.items():
        setattr(loan, field, value)

    # Auto-complete a loan once it's fully repaid, unless the caller
    # explicitly set a different status in this same request.
    if "status" not in changes:
        if loan.amount_repaid >= loan.total_repayable:
            loan.status = models.LoanStatus.COMPLETED

    db.commit()
    db.refresh(loan)

    audit_service.log_event(
        db,
        actor=current_user,
        event_type="loan.adjusted",
        action="update",
        entity_type="loan",
        entity_id=str(loan.id),
        previous_values=previous,
        new_values=changes,
        request=request,
    )

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
    """
    Change-Control note (C-3, see Phase 1 implementation report): a Loan
    is a posted financial transaction the moment it's created (there is
    no "draft" loan state anywhere in this model), so physically
    deleting one is exactly what Section 15 (Financial History
    Protection) prohibits: "Do not physically delete posted financial
    transactions." The original endpoint allowed unconditional hard
    delete; that is now blocked entirely rather than reinterpreted, since
    no correction/reversal contract for loans exists yet -- introducing
    one is Phase 3 (Accounting Foundation) scope. If a loan genuinely
    needs to be voided (e.g. created in error), that requires an
    approved correction/reversal mechanism, not deletion.
    """
    raise HTTPException(
        status_code=409,
        detail=(
            "Loans cannot be deleted; they are posted financial records. "
            "A correction/reversal mechanism for erroneous loans is planned for a later phase."
        ),
    )


@router.get("/member/{member_id}/balance", response_model=dict)
def get_member_loan_balance(
    member_id: uuid.UUID,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Running total across all of a member's active loans - the
    replacement for the spreadsheet's hardcoded loan_liabilities_helper_table
    cell-chain formulas."""
    if current_user.role == models.UserRole.MEMBER:
        if member_id != current_user.member_id:
            raise HTTPException(status_code=403, detail="You can only view your own balance")
    elif not user_has_permission(db, current_user, "loan.view"):
        raise HTTPException(status_code=403, detail="You do not have the 'loan.view' permission")

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
