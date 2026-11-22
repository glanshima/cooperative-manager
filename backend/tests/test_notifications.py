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
from app.email_utils import SENT, EmailResult
from tests.conftest import (
    auth_headers,
    grant_permission,
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


# ---------------------------------------------------------------------------
# Staff notices
# ---------------------------------------------------------------------------


def _application_payload(loan_type):
    return {
        "loan_type_id": str(loan_type.id),
        "requested_amount": "500",
        "payment_reference": "ref-notify-submit",
        "receipt_image_base64": "aGVsbG8=",
        "receipt_content_type": "image/png",
    }


def test_a_new_application_notifies_the_staff_who_can_review_it(client, db_session):
    reviewer = make_admin_user(db_session, username="notify_reviewer", super_admin=True)
    member = make_member(db_session, psn="PSN-NOT-13", name="Ada Reviewer")
    login = make_member_user(db_session, member)
    loan_type = make_loan_type(db_session, "Notify Submit Loan", open_for_application=True)

    response = client.post(
        "/api/loan-applications",
        json=_application_payload(loan_type),
        headers=auth_headers(login),
    )

    assert response.status_code == 201, response.text
    rows = _feed(db_session, reviewer)
    assert len(rows) == 1
    assert rows[0].category == models.NotificationCategory.LOAN
    assert rows[0].title == "New loan application"
    assert "Ada Reviewer" in rows[0].body
    assert rows[0].link_path == "/admin/loan-applications"
    # The applicant is not told about their own submission.
    assert _feed(db_session, login) == []


def test_a_new_application_skips_staff_without_the_review_permission(
    client, db_session, seed_permissions
):
    bystander = make_admin_user(db_session, username="notify_bystander")
    grant_permission(db_session, bystander, "loan.view")
    member = make_member(db_session, psn="PSN-NOT-14")
    login = make_member_user(db_session, member)
    loan_type = make_loan_type(db_session, "Notify Scoped Loan", open_for_application=True)

    response = client.post(
        "/api/loan-applications",
        json=_application_payload(loan_type),
        headers=auth_headers(login),
    )

    assert response.status_code == 201, response.text
    assert _feed(db_session, bystander) == []


def test_a_member_cancellation_notifies_the_staff_who_can_review_it(client, db_session):
    reviewer = make_admin_user(db_session, username="notify_cancel_reviewer", super_admin=True)
    member = make_member(db_session, psn="PSN-NOT-15", name="Ada Canceller")
    login = make_member_user(db_session, member)
    loan_type = make_loan_type(db_session, "Notify Cancel Loan")
    application = _make_application(
        db_session,
        member,
        loan_type,
        payment_status=models.PaymentVerificationStatus.AWAITING_VERIFICATION,
        status=models.LoanApplicationStatus.PENDING,
    )

    response = client.post(
        f"/api/loan-applications/{application.id}/cancel",
        headers=auth_headers(login),
    )

    assert response.status_code == 200, response.text
    rows = _feed(db_session, reviewer)
    assert len(rows) == 1
    assert rows[0].category == models.NotificationCategory.LOAN
    assert rows[0].title == "Loan application cancelled"
    assert "Ada Canceller" in rows[0].body
    assert "500" in rows[0].body
    assert rows[0].link_path == "/admin/loan-applications"
    # The member made the choice; they don't get told about it.
    assert _feed(db_session, login) == []


def test_a_member_cancellation_skips_staff_without_the_review_permission(
    client, db_session, seed_permissions
):
    bystander = make_admin_user(db_session, username="notify_cancel_bystander")
    grant_permission(db_session, bystander, "loan.view")
    member = make_member(db_session, psn="PSN-NOT-16")
    login = make_member_user(db_session, member)
    loan_type = make_loan_type(db_session, "Notify Cancel Scoped Loan")
    application = _make_application(
        db_session,
        member,
        loan_type,
        payment_status=models.PaymentVerificationStatus.VERIFIED,
        status=models.LoanApplicationStatus.APPROVED,
    )

    response = client.post(
        f"/api/loan-applications/{application.id}/cancel",
        headers=auth_headers(login),
    )

    assert response.status_code == 200, response.text
    assert _feed(db_session, bystander) == []


# ---------------------------------------------------------------------------
# Payroll deductions
# ---------------------------------------------------------------------------


def _make_deduction(db_session, member, *, status=models.PayrollDeductionStatus.SUBMITTED):
    deduction = models.PayrollDeduction(
        member_id=member.id,
        deduction_month=date(2026, 11, 1),
        status=status,
    )
    deduction.lines = [
        models.PayrollDeductionLine(
            category=models.PayrollDeductionLineCategory.MONTHLY_CONTRIBUTION,
            amount=Decimal("2000.00"),
        )
    ]
    db_session.add(deduction)
    db_session.commit()
    db_session.refresh(deduction)
    return deduction


def test_confirming_a_deduction_notifies_the_member(client, db_session):
    admin = make_admin_user(db_session, username="notify_ded_admin", super_admin=True)
    member = make_member(db_session, psn="PSN-NOT-15")
    login = make_member_user(db_session, member)
    deduction = _make_deduction(db_session, member)

    response = client.post(
        f"/api/payroll-deductions/{deduction.id}/confirm", headers=auth_headers(admin)
    )

    assert response.status_code == 200, response.text
    rows = _feed(db_session, login)
    assert len(rows) == 1
    assert rows[0].title == "Payroll deduction recorded"
    assert "November 2026" in rows[0].body
    assert "2000.00" in rows[0].body
    assert rows[0].link_path == "/dashboard"


def test_marking_a_deduction_not_deducted_tells_the_member(client, db_session):
    admin = make_admin_user(db_session, username="notify_ded_skip_admin", super_admin=True)
    member = make_member(db_session, psn="PSN-NOT-16")
    login = make_member_user(db_session, member)
    deduction = _make_deduction(db_session, member)

    response = client.post(
        f"/api/payroll-deductions/{deduction.id}/not-deducted",
        json={"reason": "Payroll omitted this PSN"},
        headers=auth_headers(admin),
    )

    assert response.status_code == 200, response.text
    rows = _feed(db_session, login)
    assert len(rows) == 1
    assert rows[0].title == "Payroll deduction not made"
    assert "Payroll omitted this PSN" in rows[0].body


# ---------------------------------------------------------------------------
# Account and security notices
# ---------------------------------------------------------------------------


def test_creating_a_member_login_welcomes_the_account(client, db_session):
    admin = make_admin_user(db_session, username="notify_welcome_admin", super_admin=True)
    member = make_member(db_session, psn="PSN-NOT-17")

    response = client.post(
        "/api/auth/create-member-login",
        json={"member_id": str(member.id), "temporary_password": "Passw0rd!"},
        headers=auth_headers(admin),
    )

    assert response.status_code == 201, response.text
    login = db_session.query(models.User).filter(models.User.member_id == member.id).one()
    rows = _feed(db_session, login)
    assert len(rows) == 1
    assert rows[0].category == models.NotificationCategory.ACCOUNT
    assert rows[0].title == "Your login is ready"


def test_changing_a_password_notifies_the_account(client, db_session):
    login = make_member_user(db_session, make_member(db_session, psn="PSN-NOT-18"))

    response = client.post(
        "/api/auth/change-password",
        json={"current_password": "Passw0rd!", "new_password": "NewPassw0rd!"},
        headers=auth_headers(login),
    )

    assert response.status_code == 200, response.text
    rows = _feed(db_session, login)
    assert len(rows) == 1
    assert rows[0].title == "Password changed"


def test_a_status_change_notifies_the_account(client, db_session):
    admin = make_admin_user(db_session, username="notify_status_admin", super_admin=True)
    login = make_member_user(db_session, make_member(db_session, psn="PSN-NOT-19"))

    response = client.patch(
        f"/api/admin/users/{login.id}/status",
        json={"account_status": "suspended", "reason": "Investigation"},
        headers=auth_headers(admin),
    )

    assert response.status_code == 200, response.text
    rows = _feed(db_session, login)
    assert len(rows) == 1
    assert rows[0].title == "Account status changed"
    assert "suspended" in rows[0].body
    assert "Investigation" in rows[0].body


# ---------------------------------------------------------------------------
# Email preferences
# ---------------------------------------------------------------------------


def test_preferences_default_to_every_optional_email_on(client, db_session):
    login = make_member_user(db_session, make_member(db_session, psn="PSN-NOT-20"))

    response = client.get("/api/notifications/preferences", headers=auth_headers(login))

    assert response.status_code == 200, response.text
    assert response.json() == {"email_loan": True, "email_repayment": True}


def test_preferences_are_stored_per_account(client, db_session):
    owner = make_member_user(db_session, make_member(db_session, psn="PSN-NOT-21"))
    other = make_member_user(db_session, make_member(db_session, psn="PSN-NOT-22"))

    updated = client.put(
        "/api/notifications/preferences",
        json={"email_loan": False},
        headers=auth_headers(owner),
    )

    assert updated.status_code == 200, updated.text
    assert updated.json() == {"email_loan": False, "email_repayment": True}
    # The partial update left the other switch alone.
    assert (
        client.get("/api/notifications/preferences", headers=auth_headers(owner)).json()
        == {"email_loan": False, "email_repayment": True}
    )
    assert (
        client.get("/api/notifications/preferences", headers=auth_headers(other)).json()
        == {"email_loan": True, "email_repayment": True}
    )


def _capture_send(monkeypatch, module_path):
    sent = []

    def fake_send(**kwargs):
        sent.append(kwargs)
        return EmailResult(True, SENT, message_id="msg_test")

    monkeypatch.setattr(f"{module_path}.send_email", fake_send)
    return sent


def test_switching_off_loan_email_skips_the_send_but_keeps_the_notice(
    client, db_session, monkeypatch
):
    sent = _capture_send(monkeypatch, "app.routers.loan_applications")
    admin = make_admin_user(db_session, username="notify_pref_admin", super_admin=True)
    member = make_member(db_session, psn="PSN-NOT-23")
    login = make_member_user(db_session, member)
    loan_type = make_loan_type(db_session, "Notify Pref Loan")
    application = _make_application(
        db_session,
        member,
        loan_type,
        payment_status=models.PaymentVerificationStatus.VERIFIED,
        status=models.LoanApplicationStatus.PENDING,
    )
    client.put(
        "/api/notifications/preferences",
        json={"email_loan": False},
        headers=auth_headers(login),
    )

    response = client.post(
        f"/api/loan-applications/{application.id}/decide",
        json={"approved": False, "admin_notes": "Not eligible", "can_reapply": True},
        headers=auth_headers(admin),
    )

    assert response.status_code == 200, response.text
    assert sent == []
    assert [row.title for row in _feed(db_session, login)] == ["Loan application not approved"]


def test_switching_off_repayment_email_skips_the_send(
    client, db_session, monkeypatch
):
    sent = _capture_send(monkeypatch, "app.routers.loan_repayments")
    admin = make_admin_user(db_session, username="notify_pref_repay_admin", super_admin=True)
    member = make_member(db_session, psn="PSN-NOT-24")
    login = make_member_user(db_session, member)
    repayment = _make_repayment(db_session, member, make_loan_type(db_session, "Notify Pref Repay"))
    client.put(
        "/api/notifications/preferences",
        json={"email_repayment": False},
        headers=auth_headers(login),
    )

    response = client.post(
        f"/api/loan-repayments/{repayment.id}/verify",
        json={"approved": True},
        headers=auth_headers(admin),
    )

    assert response.status_code == 200, response.text
    assert sent == []
    assert [row.title for row in _feed(db_session, login)] == ["Repayment verified"]

