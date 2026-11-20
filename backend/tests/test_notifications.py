"""In-app notifications (2026-11).

Two contracts are pinned down here:

  - Scoping: a notification is only ever readable or markable by the
    account it belongs to. The user id comes from the token, so an id
    from somebody else's feed is a 404, not a permission hint.
  - Producers: the flows that tell a member something in-app (loan
    decision, payment review, disbursement, repayment review,
    contribution decision) write the row with the same commit as the
    change, and a member without a login simply gets no row -- the
    business action still succeeds.
"""

from datetime import date, datetime, timedelta
from decimal import Decimal

from app import models
from tests.conftest import (
    auth_headers,
    make_admin_user,
    make_loan_type,
    make_member,
    make_member_user,
)


def _notify(db_session, user, *, title="Hello", category=models.NotificationCategory.SYSTEM,
            created_at=None, is_read=False):
    row = models.Notification(
        user_id=user.id,
        category=category,
        title=title,
        body=f"Body of {title}",
        link_path="/dashboard",
        is_read=is_read,
        read_at=datetime(2026, 11, 1) if is_read else None,
        created_at=created_at or datetime.utcnow(),
    )
    db_session.add(row)
    db_session.commit()
    db_session.refresh(row)
    return row


def _make_application(db_session, member, loan_type, *, payment_status, status):
    application = models.LoanApplication(
        member_id=member.id,
        loan_type_id=loan_type.id,
        requested_amount=Decimal("500"),
        form_fee_amount=Decimal("10"),
        payment_reference="ref-notify-1",
        receipt_image_base64="aGVsbG8=",
        receipt_content_type="image/png",
        payment_status=payment_status,
        status=status,
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
        payment_reference="repay-ref-notify",
        receipt_image_base64="aGVsbG8=",
        receipt_content_type="image/png",
        status=models.RepaymentVerificationStatus.AWAITING_VERIFICATION,
    )
    db_session.add(repayment)
    db_session.commit()
    db_session.refresh(repayment)
    return repayment


def _feed(db_session, user):
    db_session.expire_all()
    return (
        db_session.query(models.Notification)
        .filter(models.Notification.user_id == user.id)
        .order_by(models.Notification.created_at.asc())
        .all()
    )


# ---------------------------------------------------------------------------
# Reading and marking
# ---------------------------------------------------------------------------


def test_notifications_require_a_signed_in_account(client):
    assert client.get("/api/notifications").status_code == 401


def test_the_feed_is_scoped_to_the_signed_in_account(client, db_session):
    owner = make_member_user(db_session, make_member(db_session, psn="PSN-NOT-1"))
    other = make_member_user(db_session, make_member(db_session, psn="PSN-NOT-2"))
    _notify(db_session, owner, title="Mine")
    _notify(db_session, other, title="Theirs")

    response = client.get("/api/notifications", headers=auth_headers(owner))

    assert response.status_code == 200, response.text
    body = response.json()
    assert [item["title"] for item in body["items"]] == ["Mine"]
    assert body["total"] == 1
    assert body["unread_count"] == 1


def test_the_feed_is_newest_first_and_counts_unread(client, db_session):
    user = make_member_user(db_session, make_member(db_session, psn="PSN-NOT-3"))
    now = datetime.utcnow()
    _notify(db_session, user, title="Oldest", created_at=now - timedelta(hours=2))
    _notify(db_session, user, title="Middle", created_at=now - timedelta(hours=1))
    _notify(
        db_session,
        user,
        title="Newest",
        created_at=now,
        is_read=True,
    )

    body = client.get("/api/notifications", headers=auth_headers(user)).json()

    assert [item["title"] for item in body["items"]] == ["Newest", "Middle", "Oldest"]
    assert body["total"] == 3
    assert body["unread_count"] == 2
    assert body["items"][0]["is_read"] is True
    assert body["items"][0]["read_at"] is not None


def test_a_notification_cannot_be_marked_by_someone_else(client, db_session):
    owner = make_member_user(db_session, make_member(db_session, psn="PSN-NOT-4"))
    other = make_member_user(db_session, make_member(db_session, psn="PSN-NOT-5"))
    row = _notify(db_session, owner, title="Private")

    response = client.post(
        f"/api/notifications/{row.id}/read", headers=auth_headers(other)
    )

    assert response.status_code == 404
    db_session.expire_all()
    assert db_session.get(models.Notification, row.id).is_read is False


def test_marking_read_is_idempotent_and_stamps_the_time(client, db_session):
    user = make_member_user(db_session, make_member(db_session, psn="PSN-NOT-6"))
    row = _notify(db_session, user, title="Read me")

    first = client.post(f"/api/notifications/{row.id}/read", headers=auth_headers(user))
    assert first.status_code == 200, first.text
    assert first.json()["is_read"] is True
    stamped = first.json()["read_at"]
    assert stamped is not None

    second = client.post(f"/api/notifications/{row.id}/read", headers=auth_headers(user))
    assert second.status_code == 200
    assert second.json()["read_at"] == stamped


def test_mark_all_read_clears_only_the_callers_unread_rows(client, db_session):
    owner = make_member_user(db_session, make_member(db_session, psn="PSN-NOT-7"))
    other = make_member_user(db_session, make_member(db_session, psn="PSN-NOT-8"))
    _notify(db_session, owner, title="One")
    _notify(db_session, owner, title="Two")
    _notify(db_session, owner, title="Already read", is_read=True)
    _notify(db_session, other, title="Theirs")

    response = client.post("/api/notifications/read-all", headers=auth_headers(owner))

    assert response.status_code == 200, response.text
    assert response.json()["updated"] == 2
    assert all(row.is_read for row in _feed(db_session, owner))
    assert _feed(db_session, other)[0].is_read is False


# ---------------------------------------------------------------------------
# Producers
# ---------------------------------------------------------------------------


def test_a_loan_rejection_notifies_the_member_login(client, db_session):
    admin = make_admin_user(db_session, username="notify_loan_admin", super_admin=True)
    member = make_member(db_session, psn="PSN-NOT-9")
    user = make_member_user(db_session, member)
    loan_type = make_loan_type(db_session, "Notify Loan")
    application = _make_application(
        db_session,
        member,
        loan_type,
        payment_status=models.PaymentVerificationStatus.VERIFIED,
        status=models.LoanApplicationStatus.PENDING,
    )

    response = client.post(
        f"/api/loan-applications/{application.id}/decide",
        json={"approved": False, "admin_notes": "Affordability", "can_reapply": True},
        headers=auth_headers(admin),
    )

    assert response.status_code == 200, response.text
    rows = _feed(db_session, user)
    assert len(rows) == 1
    assert rows[0].category == models.NotificationCategory.LOAN
    assert rows[0].title == "Loan application not approved"
    assert "Affordability" in rows[0].body
    assert rows[0].link_path == "/dashboard"


def test_a_repayment_verification_notifies_the_member_login(client, db_session):
    admin = make_admin_user(db_session, username="notify_repay_admin", super_admin=True)
    member = make_member(db_session, psn="PSN-NOT-10")
    user = make_member_user(db_session, member)
    repayment = _make_repayment(db_session, member, make_loan_type(db_session, "Notify Repay"))

    response = client.post(
        f"/api/loan-repayments/{repayment.id}/verify",
        json={"approved": True},
        headers=auth_headers(admin),
    )

    assert response.status_code == 200, response.text
    rows = _feed(db_session, user)
    assert len(rows) == 1
    assert rows[0].category == models.NotificationCategory.REPAYMENT
    assert rows[0].title == "Repayment verified"
    assert "800.00" in rows[0].body  # remaining balance


def test_a_contribution_approval_notifies_the_member_login(client, db_session):
    admin = make_admin_user(db_session, username="notify_contrib_admin", super_admin=True)
    member = make_member(db_session, psn="PSN-NOT-11")
    user = make_member_user(db_session, member)
    bootstrap = client.put(
        f"/api/members/{member.id}",
        headers=auth_headers(admin),
        json={"monthly_contribution_amount": "5000.00"},
    )
    assert bootstrap.status_code == 200, bootstrap.text
    applied = client.post(
        "/api/members/me/contribution-change-requests",
        headers=auth_headers(user),
        json={"requested_amount": "8000.00", "reason": "Salary increase"},
    )
    assert applied.status_code == 201, applied.text

    response = client.post(
        f"/api/contribution-change-requests/{applied.json()['id']}/approve",
        json={},
        headers=auth_headers(admin),
    )

    assert response.status_code == 200, response.text
    rows = _feed(db_session, user)
    assert len(rows) == 1
    assert rows[0].category == models.NotificationCategory.CONTRIBUTION
    assert rows[0].title == "Contribution change approved"
    assert "8000.00" in rows[0].body


def test_a_member_without_a_login_still_gets_the_business_change(client, db_session):
    admin = make_admin_user(db_session, username="notify_nologin_admin", super_admin=True)
    member = make_member(db_session, psn="PSN-NOT-12")
    loan_type = make_loan_type(db_session, "No Login Loan")
    application = _make_application(
        db_session,
        member,
        loan_type,
        payment_status=models.PaymentVerificationStatus.VERIFIED,
        status=models.LoanApplicationStatus.PENDING,
    )

    response = client.post(
        f"/api/loan-applications/{application.id}/decide",
        json={"approved": False, "admin_notes": "No record", "can_reapply": False},
        headers=auth_headers(admin),
    )

    assert response.status_code == 200, response.text
    assert db_session.query(models.Notification).count() == 0
