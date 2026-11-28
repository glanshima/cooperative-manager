import json
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


def _active_loan(db_session, member):
    loan_type = make_loan_type(db_session, "Repayment Submission Loan")
    loan = models.Loan(
        member_id=member.id,
        loan_type_id=loan_type.id,
        principal=Decimal("120000.00"),
        interest_amount=Decimal("0.00"),
        net_disbursed=Decimal("120000.00"),
        total_repayable=Decimal("120000.00"),
        monthly_installment=Decimal("10000.00"),
        disbursement_date=date(2026, 1, 1),
        expected_end_date=date(2027, 1, 1),
        amount_repaid=Decimal("0.00"),
        status=models.LoanStatus.ACTIVE,
    )
    db_session.add(loan)
    db_session.commit()
    db_session.refresh(loan)
    return loan


def _payload():
    return {
        "amount_claimed": "10000.00",
        "payment_month": date.today().strftime("%Y-%m"),
        "payment_reference": "TRF-SUBMISSION",
        "receipt_image_base64": "cmVjZWlwdA==",
        "receipt_content_type": "image/png",
    }


def _fixture(db_session):
    member = make_member(db_session, psn="PSN-REPSUB", name="Ada Repayer")
    user = make_member_user(db_session, member)
    loan = _active_loan(db_session, member)
    return member, user, loan


def test_submission_queues_active_verifiers_and_audits_without_receipt(
    client, db_session, seed_permissions
):
    _, user, loan = _fixture(db_session)
    reviewer = make_admin_user(db_session, username="rep_submit_reviewer")
    grant_permission(db_session, reviewer, "repayment.verify")
    suspended = make_admin_user(db_session, username="rep_submit_suspended")
    grant_permission(db_session, suspended, "repayment.verify")
    suspended.account_status = models.AccountStatus.SUSPENDED
    pending = make_admin_user(db_session, username="rep_submit_pending")
    grant_permission(db_session, pending, "repayment.verify")
    pending.account_status = models.AccountStatus.PENDING
    bystander = make_admin_user(db_session, username="rep_submit_bystander")
    grant_permission(db_session, bystander, "loan.view")
    db_session.commit()

    response = client.post(
        f"/api/loans/{loan.id}/repayments",
        headers=auth_headers(user),
        json=_payload(),
    )

    assert response.status_code == 201, response.text
    repayment_id = response.json()["id"]
    db_session.expire_all()
    notices = (
        db_session.query(models.Notification)
        .filter(models.Notification.user_id.in_([reviewer.id, suspended.id, pending.id, bystander.id]))
        .all()
    )
    assert len(notices) == 1
    assert notices[0].user_id == reviewer.id
    assert notices[0].category == models.NotificationCategory.REPAYMENT
    assert notices[0].title == "New repayment to verify"
    assert "Ada Repayer" in notices[0].body
    assert notices[0].link_path == "/admin/loan-repayments?status=awaiting_verification"

    audit = (
        db_session.query(models.AuditEvent)
        .filter(models.AuditEvent.event_type == "repayment.submitted")
        .one()
    )
    assert audit.actor_user_id == user.id
    assert audit.entity_id == repayment_id
    assert audit.action == "submit"
    assert audit.new_values == {
        "amount_claimed": "10000.00",
        "loan_id": str(loan.id),
        "payment_month": date.today().replace(day=1).isoformat(),
    }
    assert "cmVjZWlwdA==" not in json.dumps(audit.new_values)
    assert "TRF-SUBMISSION" not in json.dumps(audit.new_values)


def test_submission_idempotency_replays_one_attempt_but_allows_a_new_attempt(
    client, db_session
):
    _, user, loan = _fixture(db_session)
    reviewer = make_admin_user(db_session, username="rep_submit_idem_reviewer", super_admin=True)
    headers = {**auth_headers(user), "Idempotency-Key": "repayment-submit-attempt-1"}

    first = client.post(
        f"/api/loans/{loan.id}/repayments", headers=headers, json=_payload()
    )
    replay = client.post(
        f"/api/loans/{loan.id}/repayments", headers=headers, json=_payload()
    )

    assert first.status_code == 201, first.text
    assert replay.status_code == 201, replay.text
    assert replay.json()["id"] == first.json()["id"]
    db_session.expire_all()
    assert db_session.query(models.LoanRepayment).filter_by(loan_id=loan.id).count() == 1
    assert (
        db_session.query(models.Notification)
        .filter_by(user_id=reviewer.id, title="New repayment to verify")
        .count()
        == 1
    )
    assert (
        db_session.query(models.AuditEvent)
        .filter_by(event_type="repayment.submitted", entity_id=first.json()["id"])
        .count()
        == 1
    )

    second_attempt = client.post(
        f"/api/loans/{loan.id}/repayments",
        headers={**auth_headers(user), "Idempotency-Key": "repayment-submit-attempt-2"},
        json=_payload(),
    )
    assert second_attempt.status_code == 201, second_attempt.text
    assert second_attempt.json()["id"] != first.json()["id"]
    db_session.expire_all()
    assert db_session.query(models.LoanRepayment).filter_by(loan_id=loan.id).count() == 2


def test_verifier_only_access_is_limited_to_pending_queue_and_evidence(
    client, db_session, seed_permissions
):
    _, user, loan = _fixture(db_session)
    verifier = make_admin_user(db_session, username="rep_pending_verifier")
    grant_permission(db_session, verifier, "repayment.verify")
    pending = models.LoanRepayment(
        loan_id=loan.id,
        member_id=loan.member_id,
        amount_claimed=Decimal("10000.00"),
        payment_reference="TRF-PENDING",
        receipt_image_base64="cmVjZWlwdA==",
        receipt_content_type="image/png",
        status=models.RepaymentVerificationStatus.AWAITING_VERIFICATION,
    )
    verified = models.LoanRepayment(
        loan_id=loan.id,
        member_id=loan.member_id,
        amount_claimed=Decimal("5000.00"),
        payment_reference="TRF-VERIFIED",
        receipt_image_base64="cmVjZWlwdA==",
        receipt_content_type="image/png",
        status=models.RepaymentVerificationStatus.VERIFIED,
    )
    db_session.add_all([pending, verified])
    db_session.commit()

    submitted = client.post(
        f"/api/loans/{loan.id}/repayments",
        headers=auth_headers(user),
        json=_payload(),
    )
    assert submitted.status_code == 201, submitted.text

    queue = client.get("/api/loan-repayments", headers=auth_headers(verifier))
    assert queue.status_code == 200, queue.text
    assert {item["id"] for item in queue.json()} == {
        str(pending.id),
        submitted.json()["id"],
    }
    assert all(
        item["status"] == "awaiting_verification" for item in queue.json()
    )

    evidence = client.get(
        f"/api/loan-repayments/{pending.id}", headers=auth_headers(verifier)
    )
    assert evidence.status_code == 200, evidence.text
    assert evidence.json()["receipt_image_base64"] == "cmVjZWlwdA=="

    assert (
        client.get(
            "/api/loan-repayments?status=verified", headers=auth_headers(verifier)
        ).status_code
        == 403
    )
    assert (
        client.get(
            f"/api/loan-repayments/{verified.id}", headers=auth_headers(verifier)
        ).status_code
        == 403
    )
