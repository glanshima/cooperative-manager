"""
Membership status rules (2026-11).

Two things that were cooperative policy but not code:

  - a non-financial member cannot open NEW credit. Every origination path
    is covered (self-service application, admin direct loan, and
    disbursement, which re-checks because approval and payout can be
    weeks apart), while loans a member already hold keep being recovered
    through payroll -- leaving doesn't erase a debt.
  - leaving the cooperative is a recorded event (when/why), not just a
    status flip, and the exit reports the savings offset the office owes
    without posting it.
"""
from datetime import date
from decimal import Decimal

from app import models
from tests.conftest import (
    auth_headers,
    grant_permission,
    make_admin_user,
    make_loan_type,
    make_member,
    make_member_user,
)


def _make_active_loan(db_session, member, loan_type, *, total_repayable, amount_repaid):
    loan = models.Loan(
        member_id=member.id,
        loan_type_id=loan_type.id,
        principal=Decimal("1000.00"),
        interest_amount=Decimal("0.00"),
        net_disbursed=Decimal("1000.00"),
        total_repayable=total_repayable,
        monthly_installment=Decimal("100.00"),
        disbursement_date=date(2026, 1, 1),
        expected_end_date=date(2027, 1, 1),
        amount_repaid=amount_repaid,
        status=models.LoanStatus.ACTIVE,
    )
    db_session.add(loan)
    db_session.commit()
    db_session.refresh(loan)
    return loan


def _make_approved_application(db_session, member, loan_type):
    application = models.LoanApplication(
        member_id=member.id,
        loan_type_id=loan_type.id,
        requested_amount=Decimal("500"),
        form_fee_amount=Decimal("10"),
        payment_reference="ref-membership-lifecycle",
        receipt_image_base64="aGVsbG8=",
        receipt_content_type="image/png",
        payment_status=models.PaymentVerificationStatus.VERIFIED,
        status=models.LoanApplicationStatus.APPROVED,
        approved_amount=Decimal("500"),
        approved_tenure_months=6,
    )
    db_session.add(application)
    db_session.commit()
    db_session.refresh(application)
    return application


def _make_contribution_deduction(db_session, member, *, month, status, amount=Decimal("2000.00")):
    deduction = models.PayrollDeduction(
        member_id=member.id,
        deduction_month=month,
        status=status,
    )
    deduction.lines = [
        models.PayrollDeductionLine(
            category=models.PayrollDeductionLineCategory.MONTHLY_CONTRIBUTION, amount=amount
        )
    ]
    db_session.add(deduction)
    db_session.commit()
    db_session.refresh(deduction)
    return deduction


def _application_payload(loan_type):
    return {
        "loan_type_id": str(loan_type.id),
        "requested_amount": "500",
        "payment_reference": "ref-membership-lifecycle",
        "receipt_image_base64": "aGVsbG8=",
        "receipt_content_type": "image/png",
    }


# ---------------------------------------------------------------------------
# New credit is for financial members only
# ---------------------------------------------------------------------------

def test_non_financial_member_cannot_apply_for_a_loan(client, db_session):
    member = make_member(
        db_session, psn="MLC-0001", email="mlc1@example.com", status=models.MemberStatus.NON_FINANCIAL
    )
    login = make_member_user(db_session, member)
    loan_type = make_loan_type(db_session, name="Withdrawal Blocked Loan", open_for_application=True)

    res = client.post("/api/loan-applications", json=_application_payload(loan_type), headers=auth_headers(login))

    assert res.status_code == 409, res.text
    assert "Non-financial members cannot take out new loans" in res.json()["detail"]


def test_financial_member_can_still_apply(client, db_session):
    member = make_member(db_session, psn="MLC-0002", email="mlc2@example.com")
    login = make_member_user(db_session, member)
    loan_type = make_loan_type(db_session, name="Financial Member Loan", open_for_application=True)

    res = client.post("/api/loan-applications", json=_application_payload(loan_type), headers=auth_headers(login))

    assert res.status_code == 201, res.text


def test_admin_cannot_open_a_direct_loan_for_a_non_financial_member(client, db_session):
    admin = make_admin_user(db_session, username="mlc_direct", super_admin=True)
    member = make_member(
        db_session, psn="MLC-0003", email="mlc3@example.com", status=models.MemberStatus.NON_FINANCIAL
    )
    loan_type = make_loan_type(db_session, name="Direct Loan Gate")

    res = client.post(
        "/api/loans",
        json={
            "member_id": str(member.id),
            "loan_type_id": str(loan_type.id),
            "principal": "500",
            "disbursement_date": "2026-11-01",
        },
        headers=auth_headers(admin),
    )

    assert res.status_code == 409, res.text
    assert db_session.query(models.Loan).filter(models.Loan.member_id == member.id).count() == 0


def test_disbursement_is_blocked_when_membership_lapsed_after_approval(client, db_session):
    """Approval and payout are separate moments; the rule is enforced at
    the moment the money actually leaves."""
    admin = make_admin_user(db_session, username="mlc_disburse", super_admin=True)
    member = make_member(db_session, psn="MLC-0004", email="mlc4@example.com")
    loan_type = make_loan_type(db_session, name="Stale Approval Loan")
    application = _make_approved_application(db_session, member, loan_type)

    member.status = models.MemberStatus.NON_FINANCIAL
    db_session.commit()

    res = client.post(
        f"/api/loan-applications/{application.id}/disburse",
        json={},
        headers=auth_headers(admin),
    )

    assert res.status_code == 409, res.text
    db_session.refresh(application)
    assert application.resulting_loan_id is None


def test_non_financial_member_keeps_repaying_an_existing_loan(client, db_session):
    """The mirror of the rule above: recovery on credit granted while the
    member was financial continues after they stop being financial."""
    admin = make_admin_user(db_session, username="mlc_recovery", super_admin=True)
    member = make_member(
        db_session, psn="MLC-0005", email="mlc5@example.com", status=models.MemberStatus.NON_FINANCIAL
    )
    loan_type = make_loan_type(db_session, name="Recovery Loan")
    loan = _make_active_loan(
        db_session, member, loan_type, total_repayable=Decimal("8000.00"), amount_repaid=Decimal("1000.00")
    )

    res = client.post(
        "/api/payroll-deductions",
        json={
            "member_id": str(member.id),
            "deduction_month": "2026-11",
            "lines": [
                {
                    "category": "loan_repayment",
                    "loan_id": str(loan.id),
                    "amount": "500.00",
                }
            ],
        },
        headers=auth_headers(admin),
    )

    assert res.status_code == 201, res.text


# ---------------------------------------------------------------------------
# Recording a membership exit
# ---------------------------------------------------------------------------

def test_withdraw_records_the_exit_and_ends_loan_eligibility(client, db_session, seed_permissions):
    admin = make_admin_user(db_session, username="mlc_withdraw")
    grant_permission(db_session, admin, "member.deactivate")
    member = make_member(db_session, psn="MLC-0006", email="mlc6@example.com")
    login = make_member_user(db_session, member)
    loan_type = make_loan_type(db_session, name="Post Exit Loan", open_for_application=True)

    res = client.post(
        f"/api/members/{member.id}/withdraw",
        json={"reason": "Member applied to withdraw"},
        headers=auth_headers(admin),
    )

    assert res.status_code == 200, res.text
    body = res.json()
    assert body["member"]["status"] == "non_financial"
    assert body["member"]["membership_exit_date"] == date.today().isoformat()
    assert body["member"]["membership_exit_reason"] == "Member applied to withdraw"
    assert body["active_loan_count"] == 0
    assert Decimal(body["savings_balance"]) == Decimal("0.00")

    after = client.post(
        "/api/loan-applications", json=_application_payload(loan_type), headers=auth_headers(login)
    )
    assert after.status_code == 409


def test_membership_exit_is_not_repeatable(client, db_session, seed_permissions):
    admin = make_admin_user(db_session, username="mlc_twice")
    grant_permission(db_session, admin, "member.deactivate")
    member = make_member(db_session, psn="MLC-0007", email="mlc7@example.com")

    first = client.post(
        f"/api/members/{member.id}/withdraw",
        json={"reason": "Left the cooperative", "exit_date": "2026-09-30"},
        headers=auth_headers(admin),
    )
    assert first.status_code == 200, first.text
    assert first.json()["member"]["membership_exit_date"] == "2026-09-30"

    second = client.post(
        f"/api/members/{member.id}/withdraw",
        json={"reason": "Again"},
        headers=auth_headers(admin),
    )
    assert second.status_code == 409
    assert "already recorded" in second.json()["detail"]


def test_exit_date_cannot_be_in_the_future(client, db_session, seed_permissions):
    admin = make_admin_user(db_session, username="mlc_future")
    grant_permission(db_session, admin, "member.deactivate")
    member = make_member(db_session, psn="MLC-0008", email="mlc8@example.com")

    res = client.post(
        f"/api/members/{member.id}/withdraw",
        json={"reason": "Not yet", "exit_date": "2099-01-01"},
        headers=auth_headers(admin),
    )

    assert res.status_code == 400, res.text
    db_session.refresh(member)
    assert member.status == models.MemberStatus.FINANCIAL
    assert member.membership_exit_date is None


def test_exit_reports_savings_against_what_is_still_owed(client, db_session, seed_permissions):
    """Savings is the accumulated monthly contribution, and only money
    payroll actually remitted counts; the difference between what is owed
    and what savings covers is what payroll keeps recovering."""
    admin = make_admin_user(db_session, username="mlc_savings")
    grant_permission(db_session, admin, "member.deactivate")
    member = make_member(db_session, psn="MLC-0009", email="mlc9@example.com")
    loan_type = make_loan_type(db_session, name="Exit Recovery Loan")
    _make_active_loan(
        db_session, member, loan_type, total_repayable=Decimal("8000.00"), amount_repaid=Decimal("1000.00")
    )

    for month in (date(2026, 1, 1), date(2026, 2, 1), date(2026, 3, 1)):
        _make_contribution_deduction(
            db_session, member, month=month, status=models.PayrollDeductionStatus.CONFIRMED
        )
    # None of these moved money, so none of them is savings.
    _make_contribution_deduction(
        db_session, member, month=date(2026, 4, 1), status=models.PayrollDeductionStatus.DRAFT
    )
    _make_contribution_deduction(
        db_session, member, month=date(2026, 5, 1), status=models.PayrollDeductionStatus.NOT_DEDUCTED
    )
    _make_contribution_deduction(
        db_session, member, month=date(2026, 6, 1), status=models.PayrollDeductionStatus.VOID
    )

    res = client.post(
        f"/api/members/{member.id}/withdraw",
        json={"reason": "Withdrawal with loan outstanding"},
        headers=auth_headers(admin),
    )

    assert res.status_code == 200, res.text
    body = res.json()
    assert Decimal(body["savings_balance"]) == Decimal("6000.00")
    assert body["active_loan_count"] == 1
    assert Decimal(body["active_loan_outstanding"]) == Decimal("7000.00")
    assert Decimal(body["payroll_recovery_still_due"]) == Decimal("1000.00")

    # The exit reports the offset; it does not apply it.
    db_session.expire_all()
    loan = db_session.query(models.Loan).filter(models.Loan.member_id == member.id).one()
    assert loan.amount_repaid == Decimal("1000.00")
    assert loan.status == models.LoanStatus.ACTIVE


def test_withdraw_requires_the_deactivate_permission(client, db_session, seed_permissions):
    admin = make_admin_user(db_session, username="mlc_unprivileged")
    grant_permission(db_session, admin, "member.view")
    member = make_member(db_session, psn="MLC-0010", email="mlc10@example.com")

    res = client.post(
        f"/api/members/{member.id}/withdraw",
        json={"reason": "Should be refused"},
        headers=auth_headers(admin),
    )

    assert res.status_code == 403, res.text
    db_session.refresh(member)
    assert member.status == models.MemberStatus.FINANCIAL


def test_conflicted_admin_cannot_record_a_membership_exit(client, db_session, seed_permissions):
    own_member = make_member(db_session, psn="MLC-0011A", email="mlc11a@example.com")
    admin = make_admin_user(db_session, username="mlc_conflicted", member_id=own_member.id)
    grant_permission(db_session, admin, "member.deactivate")
    target = make_member(db_session, psn="MLC-0011B", email="mlc11b@example.com")

    db_session.add(
        models.MemberRelationship(
            member_id=target.id,
            related_member_id=own_member.id,
            conflict_of_interest=True,
            status=models.RelationshipStatus.ACTIVE,
        )
    )
    db_session.commit()

    res = client.post(
        f"/api/members/{target.id}/withdraw",
        json={"reason": "Conflicted officer"},
        headers=auth_headers(admin),
    )

    assert res.status_code == 409, res.text
    assert res.json()["detail"]["error"] == "member_conflict"
    db_session.refresh(target)
    assert target.status == models.MemberStatus.FINANCIAL
