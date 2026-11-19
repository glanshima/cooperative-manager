"""The six transactional email workflows, verified at the endpoint level.

Each test drives the real route with the provider call mocked, so what is
proven is the wiring business code depends on: who is mailed, under which
subject, with which idempotency key, and that the mail attempt happens
after the decision is committed.
"""

from datetime import date
from decimal import Decimal

import pytest

from app import models
from app.email_utils import SENT, EmailResult
from tests.conftest import (
    auth_headers,
    grant_permission,
    make_admin_user,
    make_loan_type,
    make_member,
    make_member_user,
)

MEMBER_EMAIL = "workflow-member@example.test"


def _capture_send(monkeypatch, module_path):
    sent = []

    def fake_send(**kwargs):
        sent.append(kwargs)
        return EmailResult(True, SENT, message_id="msg_test")

    monkeypatch.setattr(f"{module_path}.send_email", fake_send)
    return sent


def _make_application(db_session, member, loan_type, *, payment_status, status):
    application = models.LoanApplication(
        member_id=member.id,
        loan_type_id=loan_type.id,
        requested_amount=Decimal("500"),
        form_fee_amount=Decimal("10"),
        payment_reference="ref-workflow-1",
        receipt_image_base64="aGVsbG8=",
        receipt_content_type="image/png",
        payment_status=payment_status,
        status=status,
        approved_amount=Decimal("500") if status == models.LoanApplicationStatus.APPROVED else None,
        approved_tenure_months=6 if status == models.LoanApplicationStatus.APPROVED else None,
    )
    db_session.add(application)
    db_session.commit()
    db_session.refresh(application)
    return application


def _make_repayment(db_session, member, loan_type):
    loan = models.Loan(
        member_id=member.id,
        loan_type_id=loan_type.id,
        principal=Decimal("1000.00"),
        interest_amount=Decimal("0.00"),
        net_disbursed=Decimal("1000.00"),
        total_repayable=Decimal("1000.00"),
        monthly_installment=Decimal("100.00"),
        disbursement_date=date(2026, 1, 1),
        expected_end_date=date(2027, 1, 1),
        amount_repaid=Decimal("0.00"),
        status=models.LoanStatus.ACTIVE,
    )
    db_session.add(loan)
    db_session.flush()
    repayment = models.LoanRepayment(
        loan_id=loan.id,
        member_id=member.id,
        amount_claimed=Decimal("200.00"),
        payment_reference="repay-ref-1",
        receipt_image_base64="aGVsbG8=",
        receipt_content_type="image/png",
        status=models.RepaymentVerificationStatus.AWAITING_VERIFICATION,
    )
    db_session.add(repayment)
    db_session.commit()
    db_session.refresh(repayment)
    return repayment


def test_disbursement_emails_the_member_after_the_loan_exists(client, db_session, monkeypatch):
    admin = make_admin_user(db_session, username="wf_disburse", super_admin=True)
    member = make_member(db_session, psn="PSN-WF-1", email=MEMBER_EMAIL)
    loan_type = make_loan_type(db_session, "Workflow Loan")
    application = _make_application(
        db_session,
        member,
        loan_type,
        payment_status=models.PaymentVerificationStatus.VERIFIED,
        status=models.LoanApplicationStatus.APPROVED,
    )
    sent = _capture_send(monkeypatch, "app.routers.loan_applications")

    response = client.post(
        f"/api/loan-applications/{application.id}/disburse",
        json={},
        headers=auth_headers(admin),
    )

    assert response.status_code == 200, response.text
    db_session.refresh(application)
    assert application.resulting_loan_id is not None

    assert len(sent) == 1
    assert sent[0]["to"] == MEMBER_EMAIL
    assert sent[0]["subject"] == "Your loan has been disbursed"
    assert sent[0]["sender_name"] == models.DEFAULT_COOPERATIVE_NAME
    assert sent[0]["idempotency_key"] == f"loan-disbursed:{application.resulting_loan_id}"


def test_payment_rejection_email_is_sent_only_after_commit(
    client, db_session, seed_permissions, monkeypatch
):
    reviewer = make_admin_user(db_session, username="wf_payment")
    grant_permission(db_session, reviewer, "loan.review", "loan.reject")
    member = make_member(db_session, psn="PSN-WF-2", email=MEMBER_EMAIL)
    loan_type = make_loan_type(db_session, "Payment Workflow Loan")
    application = _make_application(
        db_session,
        member,
        loan_type,
        payment_status=models.PaymentVerificationStatus.AWAITING_VERIFICATION,
        status=models.LoanApplicationStatus.PENDING,
    )

    status_at_send = []
    application_id = application.id

    def fake_send(**kwargs):
        db_session.expire_all()
        status_at_send.append(db_session.get(models.LoanApplication, application_id).status)
        return EmailResult(True, SENT, message_id="msg_test")

    monkeypatch.setattr("app.routers.loan_applications.send_email", fake_send)

    response = client.post(
        f"/api/loan-applications/{application.id}/verify-payment",
        json={"approved": False, "rejection_reason": "Unreadable receipt"},
        headers=auth_headers(reviewer),
    )

    assert response.status_code == 200, response.text
    assert status_at_send == [models.LoanApplicationStatus.REJECTED]


def test_repayment_verification_emails_the_member(
    client, db_session, seed_permissions, monkeypatch
):
    officer = make_admin_user(db_session, username="wf_repay")
    grant_permission(db_session, officer, "repayment.verify")
    member = make_member(db_session, psn="PSN-WF-3", email=MEMBER_EMAIL)
    loan_type = make_loan_type(db_session, "Repayment Workflow Loan")
    repayment = _make_repayment(db_session, member, loan_type)
    sent = _capture_send(monkeypatch, "app.routers.loan_repayments")

    response = client.post(
        f"/api/loan-repayments/{repayment.id}/verify",
        json={"approved": True},
        headers=auth_headers(officer),
    )

    assert response.status_code == 200, response.text
    assert len(sent) == 1
    assert sent[0]["to"] == MEMBER_EMAIL
    assert sent[0]["subject"] == "Repayment received"
    assert sent[0]["idempotency_key"] == f"repayment-verified:{repayment.id}"


def test_repayment_rejection_emails_the_member(
    client, db_session, seed_permissions, monkeypatch
):
    officer = make_admin_user(db_session, username="wf_repay_reject")
    grant_permission(db_session, officer, "repayment.verify")
    member = make_member(db_session, psn="PSN-WF-5", email=MEMBER_EMAIL)
    loan_type = make_loan_type(db_session, "Repayment Reject Loan")
    repayment = _make_repayment(db_session, member, loan_type)
    sent = _capture_send(monkeypatch, "app.routers.loan_repayments")

    response = client.post(
        f"/api/loan-repayments/{repayment.id}/verify",
        json={"approved": False, "rejection_reason": "Reference not found"},
        headers=auth_headers(officer),
    )

    assert response.status_code == 200, response.text
    assert len(sent) == 1
    assert sent[0]["to"] == MEMBER_EMAIL
    assert sent[0]["subject"] == "Your repayment could not be verified"
    assert sent[0]["idempotency_key"] == f"repayment-rejected:{repayment.id}"


def test_password_recovery_email_keeps_the_token_out_of_logs(
    client, db_session, monkeypatch, caplog
):
    member = make_member(db_session, psn="PSN-WF-4", email=MEMBER_EMAIL)
    make_member_user(db_session, member)
    sent = _capture_send(monkeypatch, "app.routers.auth")

    response = client.post(
        "/api/auth/forgot-password", json={"identifier": member.psn}
    )

    assert response.status_code == 200, response.text
    assert len(sent) == 1
    assert sent[0]["to"] == MEMBER_EMAIL
    assert sent[0]["subject"] == f"Password Reset Request - {models.DEFAULT_COOPERATIVE_NAME}"
    assert models.DEFAULT_COOPERATIVE_NAME in sent[0]["html"]
    assert "token=" not in caplog.text
