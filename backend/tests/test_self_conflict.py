"""
Mandatory tests for the conflict-of-interest guard (Controlled Phase 1
Remediation, Section 11). Covers: self-record edits, self-approval of
loan applications, self-verification of repayments, self-disbursement,
super-admin non-bypass, alternate-approver surfacing, exclusion of
conflicted approvers, the no-eligible-approver case, NULL member_id
having no inferred conflict, and the explicit no-name/email/phone-
inference guarantee.
"""
from decimal import Decimal

from tests.conftest import auth_headers, grant_permission, make_admin_user, make_member


def _make_loan_type(db_session, name="Self-Conflict Test Loan"):
    from app import models

    loan_type = models.LoanType(name=name, is_active=True)
    db_session.add(loan_type)
    db_session.commit()
    db_session.refresh(loan_type)
    return loan_type


def _make_pending_application(db_session, member, loan_type, requested_amount=Decimal("500")):
    """A loan application whose form-fee payment is already verified, so
    it's ready for a /decide call."""
    from app import models

    application = models.LoanApplication(
        member_id=member.id,
        loan_type_id=loan_type.id,
        requested_amount=requested_amount,
        form_fee_amount=Decimal("10"),
        payment_reference="ref-self-conflict",
        receipt_image_base64="aGVsbG8=",
        receipt_content_type="image/png",
        payment_status=models.PaymentVerificationStatus.VERIFIED,
        status=models.LoanApplicationStatus.PENDING,
    )
    db_session.add(application)
    db_session.commit()
    db_session.refresh(application)
    return application


def _make_approved_application(db_session, member, loan_type, approved_amount=Decimal("500")):
    from app import models

    application = _make_pending_application(db_session, member, loan_type, approved_amount)
    application.status = models.LoanApplicationStatus.APPROVED
    application.approved_amount = approved_amount
    application.approved_tenure_months = 6
    db_session.commit()
    db_session.refresh(application)
    return application


def _make_active_loan(db_session, member, principal=Decimal("1000")):
    from app import models

    loan_type = _make_loan_type(db_session, name="Self-Conflict Active Loan")
    loan = models.Loan(
        member_id=member.id,
        loan_type_id=loan_type.id,
        principal=principal,
        interest_amount=Decimal("100"),
        net_disbursed=Decimal("900"),
        total_repayable=Decimal("1100"),
        monthly_installment=Decimal("200"),
        disbursement_date="2026-01-01",
        expected_end_date="2026-07-01",
        amount_repaid=Decimal("0"),
        status=models.LoanStatus.ACTIVE,
    )
    db_session.add(loan)
    db_session.commit()
    db_session.refresh(loan)
    return loan


def _make_awaiting_repayment(db_session, loan, member, amount=Decimal("100")):
    from app import models

    repayment = models.LoanRepayment(
        loan_id=loan.id,
        member_id=member.id,
        amount_claimed=amount,
        payment_reference="ref-self-conflict-repay",
        receipt_image_base64="aGVsbG8=",
        receipt_content_type="image/png",
    )
    db_session.add(repayment)
    db_session.commit()
    db_session.refresh(repayment)
    return repayment


# ---------------------------------------------------------------------------
# 1-2: own vs. another member's record
# ---------------------------------------------------------------------------

def test_admin_cannot_modify_own_member_record(client, db_session, seed_permissions):
    member = make_member(db_session, psn="SC-001", email="sc1@example.com")
    admin = make_admin_user(db_session, username="sc_admin_1", member_id=member.id)
    grant_permission(db_session, admin, "member.update")

    res = client.put(
        f"/api/members/{member.id}",
        json={"name": "New Name"},
        headers=auth_headers(admin),
    )
    assert res.status_code == 409
    assert res.json()["detail"]["error"] == "self_conflict"


def test_admin_can_modify_another_members_record_when_authorized(client, db_session, seed_permissions):
    own_member = make_member(db_session, psn="SC-002", email="sc2@example.com")
    other_member = make_member(db_session, psn="SC-003", email="sc3@example.com")
    admin = make_admin_user(db_session, username="sc_admin_2", member_id=own_member.id)
    grant_permission(db_session, admin, "member.update")

    res = client.put(
        f"/api/members/{other_member.id}",
        json={"name": "Updated Other"},
        headers=auth_headers(admin),
    )
    assert res.status_code == 200


# ---------------------------------------------------------------------------
# 3-4: loan approval
# ---------------------------------------------------------------------------

def test_admin_cannot_approve_own_loan_application(client, db_session, seed_permissions):
    member = make_member(db_session, psn="SC-004", email="sc4@example.com")
    admin = make_admin_user(db_session, username="sc_admin_3", member_id=member.id)
    grant_permission(db_session, admin, "loan.approve")
    loan_type = _make_loan_type(db_session)
    application = _make_pending_application(db_session, member, loan_type)

    res = client.post(
        f"/api/loan-applications/{application.id}/decide",
        json={"approved": True, "approved_amount": "500", "approved_tenure_months": 6},
        headers=auth_headers(admin),
    )
    assert res.status_code == 409
    db_session.refresh(application)
    assert application.status.value == "pending"


def test_admin_can_approve_another_members_loan_application(client, db_session, seed_permissions):
    own_member = make_member(db_session, psn="SC-005", email="sc5@example.com")
    other_member = make_member(db_session, psn="SC-006", email="sc6@example.com")
    admin = make_admin_user(db_session, username="sc_admin_4", member_id=own_member.id)
    grant_permission(db_session, admin, "loan.approve")
    loan_type = _make_loan_type(db_session)
    application = _make_pending_application(db_session, other_member, loan_type)

    res = client.post(
        f"/api/loan-applications/{application.id}/decide",
        json={"approved": True, "approved_amount": "500", "approved_tenure_months": 6},
        headers=auth_headers(admin),
    )
    assert res.status_code == 200


# ---------------------------------------------------------------------------
# 5: repayment verification
# ---------------------------------------------------------------------------

def test_admin_cannot_verify_own_repayment(client, db_session, seed_permissions):
    member = make_member(db_session, psn="SC-007", email="sc7@example.com")
    admin = make_admin_user(db_session, username="sc_admin_5", member_id=member.id)
    grant_permission(db_session, admin, "repayment.verify")
    loan = _make_active_loan(db_session, member)
    repayment = _make_awaiting_repayment(db_session, loan, member)

    res = client.post(
        f"/api/loan-repayments/{repayment.id}/verify",
        json={"approved": True},
        headers=auth_headers(admin),
    )
    assert res.status_code == 409
    db_session.refresh(loan)
    assert loan.amount_repaid == Decimal("0")


# ---------------------------------------------------------------------------
# 6: disbursement
# ---------------------------------------------------------------------------

def test_admin_cannot_disburse_own_loan(client, db_session, seed_permissions):
    member = make_member(db_session, psn="SC-008", email="sc8@example.com")
    admin = make_admin_user(db_session, username="sc_admin_6", member_id=member.id)
    grant_permission(db_session, admin, "disbursement.submit")
    loan_type = _make_loan_type(db_session)
    application = _make_approved_application(db_session, member, loan_type)

    res = client.post(
        f"/api/loan-applications/{application.id}/disburse",
        json={},
        headers=auth_headers(admin),
    )
    assert res.status_code == 409
    db_session.refresh(application)
    assert application.resulting_loan_id is None


# ---------------------------------------------------------------------------
# 7: super-admin does NOT bypass
# ---------------------------------------------------------------------------

def test_super_admin_cannot_bypass_self_conflict(client, db_session, seed_permissions):
    member = make_member(db_session, psn="SC-009", email="sc9@example.com")
    admin = make_admin_user(db_session, username="sc_super_admin", member_id=member.id, super_admin=True)
    loan_type = _make_loan_type(db_session)
    application = _make_pending_application(db_session, member, loan_type)

    res = client.post(
        f"/api/loan-applications/{application.id}/decide",
        json={"approved": True, "approved_amount": "500", "approved_tenure_months": 6},
        headers=auth_headers(admin),
    )
    assert res.status_code == 409, "super-admin must NOT bypass self-conflict protection"


# ---------------------------------------------------------------------------
# 8-9: alternate approver surfaced, conflicted approvers excluded
# ---------------------------------------------------------------------------

def test_alternate_eligible_approver_is_identified_and_conflicted_ones_excluded(
    client, db_session, seed_permissions
):
    member = make_member(db_session, psn="SC-010", email="sc10@example.com")
    conflicted_admin = make_admin_user(db_session, username="sc_conflicted", member_id=member.id)
    grant_permission(db_session, conflicted_admin, "loan.approve")

    eligible_admin = make_admin_user(db_session, username="sc_eligible")
    grant_permission(db_session, eligible_admin, "loan.approve")

    loan_type = _make_loan_type(db_session)
    application = _make_pending_application(db_session, member, loan_type)

    res = client.post(
        f"/api/loan-applications/{application.id}/decide",
        json={"approved": True, "approved_amount": "500", "approved_tenure_months": 6},
        headers=auth_headers(conflicted_admin),
    )
    assert res.status_code == 409
    body = res.json()["detail"]
    approver_usernames = {a["username"] for a in body["eligible_approvers"]}
    assert "sc_eligible" in approver_usernames
    assert "sc_conflicted" not in approver_usernames
    assert body["no_eligible_approver_available"] is False


# ---------------------------------------------------------------------------
# 10: no eligible approver -> left pending, clearly reported
# ---------------------------------------------------------------------------

def test_no_eligible_approver_leaves_transaction_pending(client, db_session, seed_permissions):
    member = make_member(db_session, psn="SC-011", email="sc11@example.com")
    conflicted_admin = make_admin_user(db_session, username="sc_only_approver", member_id=member.id)
    grant_permission(db_session, conflicted_admin, "loan.approve")
    loan_type = _make_loan_type(db_session)
    application = _make_pending_application(db_session, member, loan_type)

    res = client.post(
        f"/api/loan-applications/{application.id}/decide",
        json={"approved": True, "approved_amount": "500", "approved_tenure_months": 6},
        headers=auth_headers(conflicted_admin),
    )
    assert res.status_code == 409
    body = res.json()["detail"]
    assert body["eligible_approvers"] == []
    assert body["no_eligible_approver_available"] is True

    db_session.refresh(application)
    assert application.status.value == "pending", "must never auto-approve/auto-reject on conflict"


# ---------------------------------------------------------------------------
# 11: NULL member_id -> no inferred conflict
# ---------------------------------------------------------------------------

def test_admin_with_null_member_id_has_no_conflict(client, db_session, seed_permissions):
    member = make_member(db_session, psn="SC-012", email="sc12@example.com")
    admin = make_admin_user(db_session, username="sc_unlinked_admin")  # member_id defaults to None
    grant_permission(db_session, admin, "loan.approve")
    loan_type = _make_loan_type(db_session)
    application = _make_pending_application(db_session, member, loan_type)

    res = client.post(
        f"/api/loan-applications/{application.id}/decide",
        json={"approved": True, "approved_amount": "500", "approved_tenure_months": 6},
        headers=auth_headers(admin),
    )
    assert res.status_code == 200


# ---------------------------------------------------------------------------
# 12: names/emails/phones never create an inferred mapping
# ---------------------------------------------------------------------------

def test_matching_name_or_email_does_not_create_a_conflict(client, db_session, seed_permissions):
    """An admin account that happens to share a name/email with a member
    -- but has no explicit member_id link -- must NOT be treated as
    conflicted. Only the explicit User.member_id FK counts."""
    member = make_member(db_session, psn="SC-013", name="Coincidence Person", email="coincidence@example.com")
    # Deliberately same-looking identity, but no member_id set.
    admin = make_admin_user(db_session, username="coincidence@example.com")
    grant_permission(db_session, admin, "loan.approve")
    loan_type = _make_loan_type(db_session)
    application = _make_pending_application(db_session, member, loan_type)

    res = client.post(
        f"/api/loan-applications/{application.id}/decide",
        json={"approved": True, "approved_amount": "500", "approved_tenure_months": 6},
        headers=auth_headers(admin),
    )
    assert res.status_code == 200, "matching name/email must never be used to infer a conflict"


# ---------------------------------------------------------------------------
# 13: conflict denials are audited, without credential leakage
# ---------------------------------------------------------------------------

def test_conflict_denial_is_audited_without_credential_leakage(client, db_session, seed_permissions):
    from app import models

    member = make_member(db_session, psn="SC-014", email="sc14@example.com")
    admin = make_admin_user(db_session, username="sc_audit_admin", member_id=member.id)
    grant_permission(db_session, admin, "loan.approve")
    loan_type = _make_loan_type(db_session)
    application = _make_pending_application(db_session, member, loan_type)

    res = client.post(
        f"/api/loan-applications/{application.id}/decide",
        json={"approved": True, "approved_amount": "500", "approved_tenure_months": 6},
        headers=auth_headers(admin),
    )
    assert res.status_code == 409

    event = (
        db_session.query(models.AuditEvent)
        .filter(models.AuditEvent.event_type == "conflict_of_interest.denied")
        .order_by(models.AuditEvent.created_at.desc())
        .first()
    )
    assert event is not None
    assert event.actor_user_id == admin.id
    assert event.entity_type == "loan_application"
    assert event.entity_id == str(application.id)

    serialized = str(event.previous_values) + str(event.new_values) + str(event.reason)
    for forbidden in ("password", "Passw0rd", "token", "secret", "hash"):
        assert forbidden.lower() not in serialized.lower()
