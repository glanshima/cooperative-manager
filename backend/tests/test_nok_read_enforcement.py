"""
Tests for Next-of-Kin READ enforcement (2026-11): an admin whose linked
member is connected to the target member by an active, conflict-flagged
MemberRelationship -- in EITHER direction -- must not be able to read
that member's record, loans, loan applications, or repayments.

Lists exclude conflicted members (including from `total`), direct reads
return 409 `member_conflict`, and reading one's own record stays allowed
because there is no conflict in seeing one's own data. Member
self-service reads are unaffected. Removed relationships and
conflict_of_interest=False relationships do not block.
"""
from decimal import Decimal
from datetime import date

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


def _admin_with_member(db_session, username, psn, email, *permission_codes):
    member = make_member(db_session, psn=psn, email=email)
    admin = make_admin_user(db_session, username=username, member_id=member.id)
    if permission_codes:
        grant_permission(db_session, admin, *permission_codes)
    return member, admin


def _make_application(db_session, member, loan_type):
    from app import models

    application = models.LoanApplication(
        member_id=member.id,
        loan_type_id=loan_type.id,
        requested_amount=Decimal("500"),
        form_fee_amount=Decimal("10"),
        payment_reference="ref-nok-read",
        receipt_image_base64="aGVsbG8=",
        receipt_content_type="image/png",
        payment_status=models.PaymentVerificationStatus.VERIFIED,
        status=models.LoanApplicationStatus.PENDING,
    )
    db_session.add(application)
    db_session.commit()
    db_session.refresh(application)
    return application


def _make_active_loan(db_session, member, name_suffix):
    from app import models

    loan_type = make_loan_type(db_session, name=f"NOK Read Loan {name_suffix}")
    loan = models.Loan(
        member_id=member.id,
        loan_type_id=loan_type.id,
        principal=Decimal("1000"),
        interest_amount=Decimal("100"),
        net_disbursed=Decimal("900"),
        total_repayable=Decimal("1100"),
        monthly_installment=Decimal("200"),
        disbursement_date=date(2026, 1, 1),
        expected_end_date=date(2026, 7, 1),
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
        payment_reference="ref-nok-read-repay",
        receipt_image_base64="aGVsbG8=",
        receipt_content_type="image/png",
    )
    db_session.add(repayment)
    db_session.commit()
    db_session.refresh(repayment)
    return repayment


def _assert_member_conflict(res):
    assert res.status_code == 409, res.text
    assert res.json()["detail"]["error"] == "member_conflict"


# ---------------------------------------------------------------------------
# Member list / detail
# ---------------------------------------------------------------------------

def test_member_list_excludes_nok_member_from_items_and_total(client, db_session, seed_permissions):
    own_member, admin = _admin_with_member(
        db_session, "nok_read_list_admin", "NOK-READ-LA", "nokreadla@example.com", "member.view"
    )
    target = make_member(db_session, psn="NOK-READ-LB", email="nokreadlb@example.com")
    unrelated = make_member(db_session, psn="NOK-READ-LC", email="nokreadlc@example.com")
    _link_nok(db_session, own_member, target)

    res = client.get("/api/members", params={"limit": 100}, headers=auth_headers(admin))
    assert res.status_code == 200, res.text
    body = res.json()
    psns = {item["psn"] for item in body["items"]}
    assert psns == {own_member.psn, unrelated.psn}
    assert body["total"] == 2

    # Search can't be used to walk around the list exclusion either.
    res = client.get(
        "/api/members", params={"search": target.psn}, headers=auth_headers(admin)
    )
    assert res.status_code == 200
    body = res.json()
    assert body["items"] == []
    assert body["total"] == 0


def test_member_list_shows_everything_to_unlinked_admin(client, db_session, seed_permissions):
    admin = make_admin_user(db_session, username="nok_read_unlinked_admin")
    grant_permission(db_session, admin, "member.view")
    make_member(db_session, psn="NOK-READ-UL1", email="nokreadul1@example.com")
    make_member(db_session, psn="NOK-READ-UL2", email="nokreadul2@example.com")

    res = client.get("/api/members", params={"limit": 100}, headers=auth_headers(admin))
    assert res.status_code == 200
    assert res.json()["total"] == 2


def test_member_detail_blocked_when_actor_is_the_next_of_kin(client, db_session, seed_permissions):
    own_member, admin = _admin_with_member(
        db_session, "nok_read_detail_a", "NOK-READ-DA", "nokreadda@example.com", "member.view"
    )
    target = make_member(db_session, psn="NOK-READ-DB", email="nokreaddb@example.com")
    _link_nok(db_session, own_member, target)

    res = client.get(f"/api/members/{target.id}", headers=auth_headers(admin))
    _assert_member_conflict(res)


def test_member_detail_blocked_when_target_lists_actor_as_next_of_kin(
    client, db_session, seed_permissions
):
    own_member, admin = _admin_with_member(
        db_session, "nok_read_detail_b", "NOK-READ-DC", "nokreaddc@example.com", "member.view"
    )
    target = make_member(db_session, psn="NOK-READ-DD", email="nokreaddd@example.com")
    _link_nok(db_session, target, own_member)

    res = client.get(f"/api/members/{target.id}", headers=auth_headers(admin))
    _assert_member_conflict(res)


def test_member_detail_allows_own_and_unrelated_records(client, db_session, seed_permissions):
    own_member, admin = _admin_with_member(
        db_session, "nok_read_detail_ok", "NOK-READ-DE", "nokreadde@example.com", "member.view"
    )
    unrelated = make_member(db_session, psn="NOK-READ-DF", email="nokreaddf@example.com")

    own_res = client.get(f"/api/members/{own_member.id}", headers=auth_headers(admin))
    assert own_res.status_code == 200, own_res.text

    unrelated_res = client.get(f"/api/members/{unrelated.id}", headers=auth_headers(admin))
    assert unrelated_res.status_code == 200, unrelated_res.text


def test_member_detail_allows_after_relationship_is_removed(client, db_session, seed_permissions):
    from app import models

    own_member, admin = _admin_with_member(
        db_session, "nok_read_detail_rm", "NOK-READ-DG", "nokreaddg@example.com", "member.view"
    )
    target = make_member(db_session, psn="NOK-READ-DH", email="nokreaddh@example.com")
    relationship = _link_nok(db_session, own_member, target)
    relationship.status = models.RelationshipStatus.REMOVED
    db_session.commit()

    res = client.get(f"/api/members/{target.id}", headers=auth_headers(admin))
    assert res.status_code == 200, res.text


def test_member_detail_allows_when_conflict_flag_is_false(client, db_session, seed_permissions):
    own_member, admin = _admin_with_member(
        db_session, "nok_read_detail_nf", "NOK-READ-DI", "nokreaddi@example.com", "member.view"
    )
    target = make_member(db_session, psn="NOK-READ-DJ", email="nokreaddj@example.com")
    _link_nok(db_session, own_member, target, conflict_of_interest=False)

    res = client.get(f"/api/members/{target.id}", headers=auth_headers(admin))
    assert res.status_code == 200, res.text


# ---------------------------------------------------------------------------
# Loans / applications / repayments
# ---------------------------------------------------------------------------

def test_loan_reads_blocked_and_excluded(client, db_session, seed_permissions):
    own_member, admin = _admin_with_member(
        db_session, "nok_read_loans", "NOK-READ-LO1", "nokreadlo1@example.com", "loan.view"
    )
    target = make_member(db_session, psn="NOK-READ-LO2", email="nokreadlo2@example.com")
    _link_nok(db_session, own_member, target)
    target_loan = _make_active_loan(db_session, target, "target")
    own_loan = _make_active_loan(db_session, own_member, "own")

    _assert_member_conflict(
        client.get(f"/api/loans/{target_loan.id}", headers=auth_headers(admin))
    )
    _assert_member_conflict(
        client.get(f"/api/loans/member/{target.id}/balance", headers=auth_headers(admin))
    )

    res = client.get("/api/loans", headers=auth_headers(admin))
    assert res.status_code == 200, res.text
    loan_ids = {loan["id"] for loan in res.json()}
    assert str(own_loan.id) in loan_ids
    assert str(target_loan.id) not in loan_ids

    res = client.get(
        "/api/loans", params={"member_id": str(target.id)}, headers=auth_headers(admin)
    )
    assert res.status_code == 200
    assert res.json() == []


def test_loan_application_reads_blocked_and_excluded(client, db_session, seed_permissions):
    own_member, admin = _admin_with_member(
        db_session, "nok_read_apps", "NOK-READ-AP1", "nokreadap1@example.com", "loan.view"
    )
    target = make_member(db_session, psn="NOK-READ-AP2", email="nokreadap2@example.com")
    _link_nok(db_session, own_member, target)
    loan_type = make_loan_type(db_session, name="NOK Read Applications")
    target_app = _make_application(db_session, target, loan_type)
    own_app = _make_application(db_session, own_member, loan_type)

    _assert_member_conflict(
        client.get(f"/api/loan-applications/{target_app.id}", headers=auth_headers(admin))
    )

    res = client.get("/api/loan-applications", headers=auth_headers(admin))
    assert res.status_code == 200, res.text
    app_ids = {app["id"] for app in res.json()}
    assert str(own_app.id) in app_ids
    assert str(target_app.id) not in app_ids


def test_repayment_reads_blocked_and_excluded(client, db_session, seed_permissions):
    own_member, admin = _admin_with_member(
        db_session, "nok_read_reps", "NOK-READ-RP1", "nokreadrp1@example.com", "repayment.view"
    )
    target = make_member(db_session, psn="NOK-READ-RP2", email="nokreadrp2@example.com")
    _link_nok(db_session, own_member, target)
    target_loan = _make_active_loan(db_session, target, "rep-target")
    target_repayment = _make_awaiting_repayment(db_session, target_loan, target)
    own_loan = _make_active_loan(db_session, own_member, "rep-own")
    own_repayment = _make_awaiting_repayment(db_session, own_loan, own_member)

    _assert_member_conflict(
        client.get(
            f"/api/loans/{target_loan.id}/repayments", headers=auth_headers(admin)
        )
    )
    _assert_member_conflict(
        client.get(
            f"/api/loan-repayments/{target_repayment.id}", headers=auth_headers(admin)
        )
    )

    res = client.get("/api/loan-repayments", headers=auth_headers(admin))
    assert res.status_code == 200, res.text
    repayment_ids = {repayment["id"] for repayment in res.json()}
    assert str(own_repayment.id) in repayment_ids
    assert str(target_repayment.id) not in repayment_ids


# ---------------------------------------------------------------------------
# Self-service / audit
# ---------------------------------------------------------------------------

def test_member_self_service_reads_are_unaffected(client, db_session, seed_permissions):
    """The conflicted admin's next of kin keeps full access to their own
    record and financial data."""
    admin_member = make_member(db_session, psn="NOK-READ-SF1", email="nokreadsf1@example.com")
    make_admin_user(db_session, username="nok_read_sf_admin", member_id=admin_member.id)
    target = make_member(db_session, psn="NOK-READ-SF2", email="nokreadsf2@example.com")
    target_user = make_member_user(db_session, target)
    _link_nok(db_session, admin_member, target)
    loan = _make_active_loan(db_session, target, "self-service")
    repayment = _make_awaiting_repayment(db_session, loan, target)
    loan_type = make_loan_type(db_session, name="NOK Read Self Service")
    application = _make_application(db_session, target, loan_type)

    headers = auth_headers(target_user)
    assert client.get("/api/members/me", headers=headers).status_code == 200
    assert client.get(f"/api/members/{target.id}", headers=headers).status_code == 200
    assert client.get("/api/loans", headers=headers).status_code == 200
    assert client.get(f"/api/loans/{loan.id}", headers=headers).status_code == 200
    assert client.get(f"/api/loans/{loan.id}/repayments", headers=headers).status_code == 200
    assert client.get("/api/loan-applications", headers=headers).status_code == 200
    assert client.get(f"/api/loan-applications/{application.id}", headers=headers).status_code == 200
    assert client.get(f"/api/loan-repayments/{repayment.id}", headers=headers).status_code == 200


def test_read_denial_is_audit_logged(client, db_session, seed_permissions):
    from app import models

    own_member, admin = _admin_with_member(
        db_session, "nok_read_audit", "NOK-READ-AU1", "nokreadau1@example.com", "member.view"
    )
    target = make_member(db_session, psn="NOK-READ-AU2", email="nokreadau2@example.com")
    _link_nok(db_session, own_member, target)

    res = client.get(f"/api/members/{target.id}", headers=auth_headers(admin))
    _assert_member_conflict(res)

    event = (
        db_session.query(models.AuditEvent)
        .filter(
            models.AuditEvent.event_type == "conflict_of_interest.denied",
            models.AuditEvent.entity_type == "member",
            models.AuditEvent.entity_id == str(target.id),
        )
        .first()
    )
    assert event is not None
    assert event.action == "deny"
    assert event.actor_user_id == admin.id
    assert "Next of Kin" in (event.reason or "")
