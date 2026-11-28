"""Loan application cancellation, rescheduling, and terminal payment review."""
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
from decimal import Decimal
from threading import Barrier
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event

from app import models
from app.email_utils import SENT, EmailResult
from app.main import app
from tests.conftest import (
    TestSessionLocal,
    auth_headers,
    make_admin_user,
    make_loan_type,
    make_member,
    make_member_user,
)


def _fixture(db_session, suffix):
    member = make_member(
        db_session,
        psn=f"PSN-LIFECYCLE-{suffix}",
        email=f"lifecycle-{suffix}@example.com",
    )
    user = make_member_user(db_session, member)
    loan_type = make_loan_type(db_session, f"Lifecycle Loan {suffix}")
    admin = make_admin_user(
        db_session,
        username=f"lifecycle_{suffix}",
        super_admin=True,
    )
    return member, user, loan_type, admin


def _application(
    db_session,
    member,
    loan_type,
    *,
    status=models.LoanApplicationStatus.PENDING,
    payment_status=models.PaymentVerificationStatus.AWAITING_VERIFICATION,
):
    application = models.LoanApplication(
        member_id=member.id,
        loan_type_id=loan_type.id,
        requested_amount=Decimal("500.00"),
        form_fee_amount=Decimal("0.00"),
        preferred_disbursement_date=date(2027, 1, 15),
        payment_reference="TRF-LIFECYCLE",
        receipt_image_base64="aGVsbG8=",
        receipt_content_type="image/png",
        payment_status=payment_status,
        status=status,
        admin_notes="Existing terminal decision",
        cancelled_at=datetime(2026, 11, 20, 9, 0, 0)
        if status == models.LoanApplicationStatus.CANCELLED
        else None,
    )
    db_session.add(application)
    db_session.commit()
    db_session.refresh(application)
    return application


@pytest.mark.parametrize(
    "application_status",
    [
        models.LoanApplicationStatus.CANCELLED,
        models.LoanApplicationStatus.REJECTED,
    ],
)
@pytest.mark.parametrize("approved", [True, False])
def test_payment_review_preserves_terminal_application_status(
    client, db_session, monkeypatch, application_status, approved
):
    member, user, loan_type, admin = _fixture(db_session, uuid4().hex[:8])
    application = _application(db_session, member, loan_type, status=application_status)
    original_cancelled_at = application.cancelled_at
    monkeypatch.setattr(
        "app.routers.loan_applications.send_email",
        lambda **kwargs: EmailResult(True, SENT, message_id="msg_lifecycle_test"),
    )

    response = client.post(
        f"/api/loan-applications/{application.id}/verify-payment",
        json={
            "approved": approved,
            "rejection_reason": None if approved else "Receipt unreadable",
        },
        headers=auth_headers(admin),
    )

    assert response.status_code == 200, response.text
    assert response.json()["status"] == application_status.value
    assert response.json()["payment_status"] == (
        "verified" if approved else "rejected"
    )
    assert response.json()["admin_notes"] == "Existing terminal decision"
    assert response.json()["payment_reference"] == "TRF-LIFECYCLE"
    detail = client.get(
        f"/api/loan-applications/{application.id}", headers=auth_headers(user)
    )
    assert detail.status_code == 200, detail.text
    assert detail.json()["receipt_image_base64"] == "aGVsbG8="

    db_session.refresh(application)
    assert application.status == application_status
    assert application.cancelled_at == original_cancelled_at
    assert application.payment_verified_by_user_id == admin.id
    assert application.payment_verified_at is not None
    if not approved:
        assert application.payment_rejection_reason == "Receipt unreadable"

    audit = (
        db_session.query(models.AuditEvent)
        .filter(
            models.AuditEvent.entity_type == "loan_application",
            models.AuditEvent.entity_id == str(application.id),
            models.AuditEvent.event_type
            == ("loan_application.payment_verified" if approved else "loan_application.payment_rejected"),
        )
        .one()
    )
    assert audit.previous_values["application_status"] == application_status.value
    assert audit.new_values["application_status"] == application_status.value

    if approved:
        decision = client.post(
            f"/api/loan-applications/{application.id}/decide",
            json={"approved": True, "approved_amount": "500.00", "approved_tenure_months": 6},
            headers=auth_headers(admin),
        )
        assert decision.status_code == 400
        assert "already been decided" in decision.json()["detail"]


def test_cancellation_replay_creates_one_notification_and_audit_event(
    client, db_session
):
    _, user, loan_type, admin = _fixture(db_session, uuid4().hex[:8])
    application = _application(db_session, user.member, loan_type)
    headers = {**auth_headers(user), "Idempotency-Key": "cancel-lifecycle-1"}
    url = f"/api/loan-applications/{application.id}/cancel"

    first = client.post(url, headers=headers)
    replay = client.post(url, headers=headers)

    assert first.status_code == 200, first.text
    assert replay.status_code == 200, replay.text
    assert replay.json() == first.json()
    assert (
        db_session.query(models.Notification)
        .filter(
            models.Notification.user_id == admin.id,
            models.Notification.title == "Loan application cancelled",
        )
        .count()
        == 1
    )
    cancellation_audits = (
        db_session.query(models.AuditEvent)
        .filter(
            models.AuditEvent.entity_type == "loan_application",
            models.AuditEvent.entity_id == str(application.id),
            models.AuditEvent.event_type == "loan_application.cancelled",
        )
        .all()
    )
    assert len(cancellation_audits) == 1
    assert cancellation_audits[0].previous_values == {"application_status": "pending"}
    assert cancellation_audits[0].new_values == {"application_status": "cancelled"}
    assert (
        db_session.query(models.IdempotencyRecord)
        .filter(
            models.IdempotencyRecord.user_id == user.id,
            models.IdempotencyRecord.idempotency_key == "cancel-lifecycle-1",
        )
        .count()
        == 1
    )

    different_attempt = client.post(
        url,
        headers={**auth_headers(user), "Idempotency-Key": "cancel-lifecycle-2"},
    )
    assert different_attempt.status_code == 400
    assert (
        db_session.query(models.AuditEvent)
        .filter(
            models.AuditEvent.entity_id == str(application.id),
            models.AuditEvent.event_type == "loan_application.cancelled",
        )
        .count()
        == 1
    )


def test_reschedule_locks_the_application_and_audits_one_retry(
    client, db_session
):
    member, user, loan_type, _ = _fixture(db_session, uuid4().hex[:8])
    application = _application(db_session, member, loan_type)
    statements = []

    def capture_sql(conn, cursor, statement, parameters, context, executemany):
        statements.append(" ".join(statement.upper().split()))

    bind = db_session.get_bind()
    event.listen(bind, "before_cursor_execute", capture_sql)
    try:
        headers = {**auth_headers(user), "Idempotency-Key": "reschedule-lifecycle-1"}
        url = f"/api/loan-applications/{application.id}/reschedule"
        payload = {"preferred_disbursement_date": "2027-02-10"}
        first = client.post(url, json=payload, headers=headers)
        replay = client.post(url, json=payload, headers=headers)
    finally:
        event.remove(bind, "before_cursor_execute", capture_sql)

    assert first.status_code == 200, first.text
    assert replay.status_code == 200, replay.text
    assert replay.json() == first.json()
    assert first.json()["preferred_disbursement_date"] == "2027-02-10"
    assert any(
        "FROM LOAN_APPLICATIONS" in statement and "FOR UPDATE" in statement
        for statement in statements
    )
    audits = (
        db_session.query(models.AuditEvent)
        .filter(
            models.AuditEvent.entity_type == "loan_application",
            models.AuditEvent.entity_id == str(application.id),
            models.AuditEvent.event_type == "loan_application.rescheduled",
        )
        .all()
    )
    assert len(audits) == 1
    assert audits[0].action == "reschedule"
    assert audits[0].previous_values == {"preferred_disbursement_date": "2027-01-15"}
    assert audits[0].new_values == {"preferred_disbursement_date": "2027-02-10"}


def test_concurrent_cancellations_create_only_one_terminal_transition():
    setup = TestSessionLocal()
    suffix = uuid4().hex[:8]
    member = user = loan_type = admin = application = None
    try:
        member, user, loan_type, admin = _fixture(setup, suffix)
        application = _application(setup, member, loan_type)
        barrier = Barrier(2)

        def cancel(_):
            with TestClient(app) as test_client:
                barrier.wait()
                return test_client.post(
                    f"/api/loan-applications/{application.id}/cancel",
                    headers=auth_headers(user),
                )

        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(pool.map(cancel, [0, 1]))

        assert sorted(response.status_code for response in responses) == [200, 400]
        setup.expire_all()
        stored = setup.get(models.LoanApplication, application.id)
        assert stored.status == models.LoanApplicationStatus.CANCELLED
        assert stored.cancelled_at is not None
        assert (
            setup.query(models.Notification)
            .filter(
                models.Notification.user_id == admin.id,
                models.Notification.title == "Loan application cancelled",
            )
            .count()
            == 1
        )
        assert (
            setup.query(models.AuditEvent)
            .filter(
                models.AuditEvent.entity_type == "loan_application",
                models.AuditEvent.entity_id == str(application.id),
                models.AuditEvent.event_type == "loan_application.cancelled",
            )
            .count()
            == 1
        )
    finally:
        setup.rollback()
        if application is not None:
            setup.query(models.AuditEvent).filter(
                models.AuditEvent.entity_type == "loan_application",
                models.AuditEvent.entity_id == str(application.id),
            ).delete(synchronize_session=False)
            setup.query(models.Notification).filter(
                models.Notification.user_id == admin.id
            ).delete(synchronize_session=False)
            setup.query(models.LoanApplication).filter(
                models.LoanApplication.id == application.id
            ).delete(synchronize_session=False)
        if user is not None:
            setup.query(models.User).filter(models.User.id == user.id).delete(
                synchronize_session=False
            )
        if admin is not None:
            setup.query(models.User).filter(models.User.id == admin.id).delete(
                synchronize_session=False
            )
        if loan_type is not None:
            setup.query(models.LoanType).filter(models.LoanType.id == loan_type.id).delete(
                synchronize_session=False
            )
        if member is not None:
            setup.query(models.Member).filter(models.Member.id == member.id).delete(
                synchronize_session=False
            )
        setup.commit()
        setup.close()
