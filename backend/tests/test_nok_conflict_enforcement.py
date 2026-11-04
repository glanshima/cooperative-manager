"""
Tests for Next-of-Kin conflict enforcement (2026-11): an admin whose
linked member is connected to the target member by an active,
conflict-flagged MemberRelationship -- in EITHER direction -- must be
blocked from acting on that member's records, exactly like the
self-conflict guard blocks acting on their own.

Covers every administrative mutation endpoint the guard was wired into:
member edit / login-status / delete, direct loan creation, loan
adjustment, loan-application payment verification / decision /
disbursement, repayment verification, and member-login creation /
password reset. Also covers the non-blocking cases (removed
relationship, conflict_of_interest=False, unrelated member, self-service
actions) and the alternate-approver exclusion.
"""
from decimal import Decimal

from tests.conftest import (
    auth_headers,
    grant_permission,
    make_admin_user,
    make_loan_type,
    make_member,
    make_member_user,
)


def _link_nok(db_session, member, related_member, conflict_of_interest=True, status=None):
    from app import models

    relationship = models.MemberRelationship(
        member_id=member.id,
        related_member_id=related_member.id,
        conflict_of_interest=conflict_of_interest,
        status=status or models.RelationshipStatus.ACTIVE,
    )
    db_session.add(relationship)
    db_session.commit()
    db_session.refresh(relationship)
    return relationship


def _admin_with_member(db_session, username, psn, email, *permission_codes, super_admin=False):
    member = make_member(db_session, psn=psn, email=email)
    admin = make_admin_user(db_session, username=username, member_id=member.id, super_admin=super_admin)
    if permission_codes:
        grant_permission(db_session, admin, *permission_codes)
    return member, admin


def _make_application(db_session, member, loan_type, *, payment_status=None, status=None):
    from app import models

    application = models.LoanApplication(
        member_id=member.id,
        loan_type_id=loan_type.id,
        requested_amount=Decimal("500"),
        form_fee_amount=Decimal("10"),
        payment_reference="ref-nok-conflict",
        receipt_image_base64="aGVsbG8=",
        receipt_content_type="image/png",
        payment_status=payment_status or models.PaymentVerificationStatus.VERIFIED,
        status=status or models.LoanApplicationStatus.PENDING,
    )
    db_session.add(application)
    db_session.commit()
    db_session.refresh(application)
    return application


def _make_approved_application(db_session, member, loan_type):
    from app import models

    application = _make_application(db_session, member, loan_type)
    application.status = models.LoanApplicationStatus.APPROVED
    application.approved_amount = Decimal("500")
    application.approved_tenure_months = 6
    db_session.commit()
    db_session.refresh(application)
    return application


def _make_active_loan(db_session, member):
    from app import models

    loan_type = make_loan_type(db_session, name="NOK Conflict Active Loan")
    loan = models.Loan(
        member_id=member.id,
        loan_type_id=loan_type.id,
        principal=Decimal("1000"),
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


def _make_awaiting_repayment(db_session, loan, member):
    from app import models

    repayment = models.LoanRepayment(
        loan_id=loan.id,
        member_id=member.id,
        amount_claimed=Decimal("100"),
        payment_reference="ref-nok-conflict-repay",
        receipt_image_base64="aGVsbG8=",
        receipt_content_type="image/png",
    )
    db_session.add(repayment)
    db_session.commit()
    db_session.refresh(repayment)
    return repayment


# ---------------------------------------------------------------------------
# Direction / status of the relationship
# ---------------------------------------------------------------------------

def test_admin_cannot_edit_member_who_lists_them_as_next_of_kin(client, db_session, seed_permissions):
    """Target's record names the actor as Next of Kin (target -> actor)."""
    own_member, admin = _admin_with_member(
        db_session, "nok_dir1_admin", "NOK-DIR-1A", "nokdir1a@example.com", "member.update"
    )
    target = make_member(db_session, psn="NOK-DIR-1B", email="nokdir1b@example.com")
    _link_nok(db_session, target, own_member)  # target's NOK is the admin's member

    res = client.put(
        f"/api/members/{target.id}",
        json={"name": "Changed By NOK"},
        headers=auth_headers(admin),
    )
    assert res.status_code == 409
    body = res.json()["detail"]
    assert body["error"] == "member_conflict"

    db_session.refresh(target)
    assert target.name != "Changed By NOK"


def test_admin_cannot_edit_member_listed_as_their_own_next_of_kin(client, db_session, seed_permissions):
    """The actor's record names the target as Next of Kin (actor -> target)."""
    own_member, admin = _admin_with_member(
        db_session, "nok_dir2_admin", "NOK-DIR-2A", "nokdir2a@example.com", "member.update"
    )
    target = make_member(db_session, psn="NOK-DIR-2B", email="nokdir2b@example.com")
    _link_nok(db_session, own_member, target)  # admin's NOK is the target

    res = client.put(
        f"/api/members/{target.id}",
        json={"name": "Changed Reverse"},
        headers=auth_headers(admin),
    )
    assert res.status_code == 409
    assert res.json()["detail"]["error"] == "member_conflict"


def test_removed_relationship_does_not_block(client, db_session, seed_permissions):
    from app import models

    own_member, admin = _admin_with_member(
        db_session, "nok_removed_admin", "NOK-REM-1A", "nokrem1a@example.com", "member.update"
    )
    target = make_member(db_session, psn="NOK-REM-1B", email="nokrem1b@example.com")
    _link_nok(db_session, target, own_member, status=models.RelationshipStatus.REMOVED)

    res = client.put(
        f"/api/members/{target.id}",
        json={"name": "Allowed After Removal"},
        headers=auth_headers(admin),
    )
    assert res.status_code == 200
    assert res.json()["name"] == "Allowed After Removal"


def test_relationship_not_flagged_as_conflict_does_not_block(client, db_session, seed_permissions):
    own_member, admin = _admin_with_member(
        db_session, "nok_noflag_admin", "NOK-NF-1A", "noknf1a@example.com", "member.update"
    )
    target = make_member(db_session, psn="NOK-NF-1B", email="noknf1b@example.com")
    _link_nok(db_session, target, own_member, conflict_of_interest=False)

    res = client.put(
        f"/api/members/{target.id}",
        json={"name": "Allowed Without Flag"},
        headers=auth_headers(admin),
    )
    assert res.status_code == 200


def test_unrelated_member_is_not_blocked(client, db_session, seed_permissions):
    own_member, admin = _admin_with_member(
        db_session, "nok_unrel_admin", "NOK-UN-1A", "nokun1a@example.com", "member.update"
    )
    target = make_member(db_session, psn="NOK-UN-1B", email="nokun1b@example.com")
    other = make_member(db_session, psn="NOK-UN-1C", email="nokun1c@example.com")
    _link_nok(db_session, target, other)  # target's NOK is someone else

    res = client.put(
        f"/api/members/{target.id}",
        json={"name": "Allowed Unrelated"},
        headers=auth_headers(admin),
    )
    assert res.status_code == 200


def test_self_conflict_still_uses_self_conflict_error_code(client, db_session, seed_permissions):
    own_member, admin = _admin_with_member(
        db_session, "nok_self_admin", "NOK-SELF-1A", "nokself1a@example.com", "member.update"
    )

    res = client.put(
        f"/api/members/{own_member.id}",
        json={"name": "Self Edit"},
        headers=auth_headers(admin),
    )
    assert res.status_code == 409
    assert res.json()["detail"]["error"] == "self_conflict"


def test_member_self_service_is_not_blocked_by_own_nok_relationship(client, db_session, seed_permissions):
    """A member submitting their OWN application resolves to the same
    member id on both sides -- never a conflict pairing."""
    member = make_member(db_session, psn="NOK-SS-1A", email="nokss1a@example.com")
    nok = make_member(db_session, psn="NOK-SS-1B", email="nokss1b@example.com")
    _link_nok(db_session, member, nok)
    login = make_member_user(db_session, member)
    loan_type = make_loan_type(
        db_session, name="NOK Self Service Loan", open_for_application=True
    )

    res = client.post(
        "/api/loan-applications",
        json={
            "loan_type_id": str(loan_type.id),
            "requested_amount": "500",
            "payment_reference": "ref-self-service",
            "receipt_image_base64": "aGVsbG8=",
            "receipt_content_type": "image/png",
        },
        headers=auth_headers(login),
    )
    assert res.status_code == 201
    assert res.json()["member_id"] == str(member.id)


# ---------------------------------------------------------------------------
# Financial mutation endpoints
# ---------------------------------------------------------------------------

def test_admin_cannot_verify_payment_for_next_of_kins_application(client, db_session, seed_permissions):
    from app import models

    own_member, admin = _admin_with_member(
        db_session, "nok_pay_admin", "NOK-PAY-1A", "nokpay1a@example.com", "loan.review"
    )
    target = make_member(db_session, psn="NOK-PAY-1B", email="nokpay1b@example.com")
    _link_nok(db_session, target, own_member)
    loan_type = make_loan_type(db_session, name="NOK Payment Loan")
    application = _make_application(
        db_session,
        target,
        loan_type,
        payment_status=models.PaymentVerificationStatus.AWAITING_VERIFICATION,
    )

    res = client.post(
        f"/api/loan-applications/{application.id}/verify-payment",
        json={"approved": True},
        headers=auth_headers(admin),
    )
    assert res.status_code == 409
    assert res.json()["detail"]["error"] == "member_conflict"

    db_session.refresh(application)
    assert application.payment_status == models.PaymentVerificationStatus.AWAITING_VERIFICATION


def test_admin_cannot_decide_next_of_kins_loan_application(client, db_session, seed_permissions):
    from app import models

    own_member, admin = _admin_with_member(
        db_session, "nok_decide_admin", "NOK-DEC-1A", "nokdec1a@example.com", "loan.approve"
    )
    target = make_member(db_session, psn="NOK-DEC-1B", email="nokdec1b@example.com")
    _link_nok(db_session, own_member, target)  # reverse direction
    loan_type = make_loan_type(db_session, name="NOK Decision Loan")
    application = _make_application(db_session, target, loan_type)

    res = client.post(
        f"/api/loan-applications/{application.id}/decide",
        json={"approved": True, "approved_amount": "500", "approved_tenure_months": 6},
        headers=auth_headers(admin),
    )
    assert res.status_code == 409
    assert res.json()["detail"]["error"] == "member_conflict"

    db_session.refresh(application)
    assert application.status == models.LoanApplicationStatus.PENDING


def test_admin_cannot_disburse_next_of_kins_loan(client, db_session, seed_permissions):
    own_member, admin = _admin_with_member(
        db_session, "nok_disb_admin", "NOK-DIS-1A", "nokdis1a@example.com", "disbursement.submit"
    )
    target = make_member(db_session, psn="NOK-DIS-1B", email="nokdis1b@example.com")
    _link_nok(db_session, target, own_member)
    loan_type = make_loan_type(db_session, name="NOK Disburse Loan")
    application = _make_approved_application(db_session, target, loan_type)

    res = client.post(
        f"/api/loan-applications/{application.id}/disburse",
        json={},
        headers=auth_headers(admin),
    )
    assert res.status_code == 409
    assert res.json()["detail"]["error"] == "member_conflict"

    db_session.refresh(application)
    assert application.resulting_loan_id is None


def test_admin_cannot_adjust_next_of_kins_loan(client, db_session, seed_permissions):
    from app import models

    own_member, admin = _admin_with_member(
        db_session, "nok_adjust_admin", "NOK-ADJ-1A", "nokadj1a@example.com", "accounting.adjust"
    )
    target = make_member(db_session, psn="NOK-ADJ-1B", email="nokadj1b@example.com")
    _link_nok(db_session, target, own_member)
    loan = _make_active_loan(db_session, target)

    res = client.put(
        f"/api/loans/{loan.id}",
        json={"notes": "tampered by NOK"},
        headers=auth_headers(admin),
    )
    assert res.status_code == 409
    assert res.json()["detail"]["error"] == "member_conflict"

    db_session.refresh(loan)
    assert loan.notes != "tampered by NOK"
    assert loan.status == models.LoanStatus.ACTIVE


def test_admin_cannot_create_direct_loan_for_next_of_kin(client, db_session, seed_permissions):
    """Direct POST /api/loans previously had no conflict guard at all --
    neither self nor Next-of-Kin."""
    from app import models

    own_member, admin = _admin_with_member(
        db_session, "nok_direct_admin", "NOK-DIRECT-1A", "nokdirect1a@example.com", "disbursement.submit"
    )
    target = make_member(db_session, psn="NOK-DIRECT-1B", email="nokdirect1b@example.com")
    _link_nok(db_session, target, own_member)
    loan_type = make_loan_type(db_session, name="NOK Direct Loan")

    res = client.post(
        "/api/loans",
        json={
            "member_id": str(target.id),
            "loan_type_id": str(loan_type.id),
            "principal": "1000",
            "disbursement_date": "2026-02-01",
        },
        headers=auth_headers(admin),
    )
    assert res.status_code == 409
    assert res.json()["detail"]["error"] == "member_conflict"

    assert (
        db_session.query(models.Loan).filter(models.Loan.member_id == target.id).count() == 0
    ), "no Loan row may be created when the conflict guard rejects the action"


def test_admin_cannot_verify_next_of_kins_repayment(client, db_session, seed_permissions):
    own_member, admin = _admin_with_member(
        db_session, "nok_repay_admin", "NOK-REP-1A", "nokrep1a@example.com", "repayment.verify"
    )
    target = make_member(db_session, psn="NOK-REP-1B", email="nokrep1b@example.com")
    _link_nok(db_session, target, own_member)
    loan = _make_active_loan(db_session, target)
    repayment = _make_awaiting_repayment(db_session, loan, target)

    res = client.post(
        f"/api/loan-repayments/{repayment.id}/verify",
        json={"approved": True},
        headers=auth_headers(admin),
    )
    assert res.status_code == 409
    assert res.json()["detail"]["error"] == "member_conflict"

    db_session.refresh(loan)
    assert loan.amount_repaid == Decimal("0")


# ---------------------------------------------------------------------------
# Member lifecycle / account takeover surfaces
# ---------------------------------------------------------------------------

def test_admin_cannot_change_next_of_kins_login_status_or_delete_them(client, db_session, seed_permissions):
    own_member, admin = _admin_with_member(
        db_session, "nok_life_admin", "NOK-LIFE-1A", "noklife1a@example.com", "member.deactivate"
    )
    target = make_member(db_session, psn="NOK-LIFE-1B", email="noklife1b@example.com")
    _link_nok(db_session, target, own_member)
    make_member_user(db_session, target)

    status_res = client.patch(
        f"/api/members/{target.id}/login-status",
        json={"account_status": "suspended"},
        headers=auth_headers(admin),
    )
    assert status_res.status_code == 409
    assert status_res.json()["detail"]["error"] == "member_conflict"

    delete_res = client.delete(f"/api/members/{target.id}", headers=auth_headers(admin))
    assert delete_res.status_code == 409
    assert delete_res.json()["detail"]["error"] == "member_conflict"


def test_admin_cannot_create_or_reset_next_of_kins_login(client, db_session, seed_permissions):
    own_member, admin = _admin_with_member(
        db_session, "nok_login_admin", "NOK-LOGIN-1A", "noklogin1a@example.com"
    )
    target = make_member(db_session, psn="NOK-LOGIN-1B", email="noklogin1b@example.com")
    _link_nok(db_session, own_member, target)  # reverse direction

    create_res = client.post(
        "/api/auth/create-member-login",
        json={"member_id": str(target.id), "temporary_password": "Passw0rd!"},
        headers=auth_headers(admin),
    )
    assert create_res.status_code == 409
    assert create_res.json()["detail"]["error"] == "member_conflict"

    make_member_user(db_session, target)
    reset_res = client.post(
        "/api/auth/reset-member-password",
        json={"member_id": str(target.id), "temporary_password": "Passw0rd!"},
        headers=auth_headers(admin),
    )
    assert reset_res.status_code == 409
    assert reset_res.json()["detail"]["error"] == "member_conflict"


# ---------------------------------------------------------------------------
# Alternate approvers
# ---------------------------------------------------------------------------

def test_eligible_approvers_exclude_officers_who_are_next_of_kin_of_target(client, db_session, seed_permissions):
    caller_member, caller = _admin_with_member(
        db_session, "nok_ea2_caller", "NOK-EA-2A", "nokea2a@example.com", "loan.approve"
    )
    target = make_member(db_session, psn="NOK-EA-2B", email="nokea2b@example.com")
    _link_nok(db_session, target, caller_member)

    nok_admin_member = make_member(db_session, psn="NOK-EA-2C", email="nokea2c@example.com")
    nok_admin = make_admin_user(db_session, username="nok_ea2_nok", member_id=nok_admin_member.id)
    grant_permission(db_session, nok_admin, "loan.approve")
    # The candidate's own record names the target as Next of Kin --
    # reverse direction, so both relationships can be active.
    _link_nok(db_session, nok_admin_member, target)

    clean_admin = make_admin_user(db_session, username="nok_ea2_clean")
    grant_permission(db_session, clean_admin, "loan.approve")

    loan_type = make_loan_type(db_session, name="NOK Eligible Approver Loan 2")
    application = _make_application(db_session, target, loan_type)

    res = client.post(
        f"/api/loan-applications/{application.id}/decide",
        json={"approved": True, "approved_amount": "500", "approved_tenure_months": 6},
        headers=auth_headers(caller),
    )
    assert res.status_code == 409
    detail = res.json()["detail"]
    approver_usernames = {a["username"] for a in detail["eligible_approvers"]}
    assert "nok_ea2_clean" in approver_usernames
    assert "nok_ea2_nok" not in approver_usernames
    assert "nok_ea2_caller" not in approver_usernames


# ---------------------------------------------------------------------------
# Audit trail
# ---------------------------------------------------------------------------

def test_nok_conflict_denial_is_audited(client, db_session, seed_permissions):
    from app import models

    own_member, admin = _admin_with_member(
        db_session, "nok_audit_admin", "NOK-AUD-1A", "nokaud1a@example.com", "loan.approve"
    )
    target = make_member(db_session, psn="NOK-AUD-1B", email="nokaud1b@example.com")
    _link_nok(db_session, target, own_member)
    loan_type = make_loan_type(db_session, name="NOK Audit Loan")
    application = _make_application(db_session, target, loan_type)

    res = client.post(
        f"/api/loan-applications/{application.id}/decide",
        json={"approved": True, "approved_amount": "500", "approved_tenure_months": 6},
        headers=auth_headers(admin),
    )
    assert res.status_code == 409

    event = (
        db_session.query(models.AuditEvent)
        .filter(models.AuditEvent.event_type == "conflict_of_interest.denied")
        .order_by(models.AuditEvent.timestamp.desc())
        .first()
    )
    assert event is not None
    assert event.actor_user_id == admin.id
    assert event.entity_type == "loan_application"
    assert event.entity_id == str(application.id)
    assert "Next of Kin" in (event.reason or "")
