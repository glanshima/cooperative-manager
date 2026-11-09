"""
Tests for the conflict-of-interest READ policy (2026-11).

The contract these tests pin down:

  - An admin whose linked member is connected to the target member by an
    active, conflict-flagged MemberRelationship -- in EITHER direction --
    can still READ that member's record, loans, applications, repayments
    and payroll deductions. Nothing is hidden and no count shrinks:
    separation of duties is about who may CHANGE a record, not who may
    see it.
  - Every such row arrives with `conflicted: true` so the caller can
    present it read-only.
  - A conflicted view leaves an audit trail
    (conflict_of_interest.viewed) that does not fail the request.
  - Actions remain refused: the same officer still gets 409
    `member_conflict` when they try to change the record.
  - Reading one's OWN record is never flagged -- there is no conflict in
    seeing one's own data -- and member self-service reads are
    unaffected. Removed relationships and conflict_of_interest=False
    relationships are not flagged either.
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


# ---------------------------------------------------------------------------
# Member list / detail
# ---------------------------------------------------------------------------

def test_member_list_keeps_the_conflicted_member_in_items_and_total(
    client, db_session, seed_permissions
):
    own_member, admin = _admin_with_member(
        db_session, "nok_read_list_admin", "NOK-READ-LA", "nokreadla@example.com", "member.view"
    )
    target = make_member(db_session, psn="NOK-READ-LB", email="nokreadlb@example.com")
    unrelated = make_member(db_session, psn="NOK-READ-LC", email="nokreadlc@example.com")
    _link_nok(db_session, own_member, target)

    res = client.get("/api/members", params={"limit": 100}, headers=auth_headers(admin))
    assert res.status_code == 200, res.text
    body = res.json()
    by_psn = {item["psn"]: item for item in body["items"]}
    assert set(by_psn) == {own_member.psn, target.psn, unrelated.psn}
    assert body["total"] == 3
    assert by_psn[target.psn]["conflicted"] is True
    assert by_psn[own_member.psn]["conflicted"] is False
    assert by_psn[unrelated.psn]["conflicted"] is False

    # Search reaches the conflicted record too -- it is a record the
    # officer is allowed to see, not a gap in the register.
    res = client.get(
        "/api/members", params={"search": target.psn}, headers=auth_headers(admin)
    )
    assert res.status_code == 200
    body = res.json()
    assert body["total"] == 1
    assert body["items"][0]["psn"] == target.psn
    assert body["items"][0]["conflicted"] is True


def test_member_list_flags_nothing_for_an_unlinked_admin(client, db_session, seed_permissions):
    admin = make_admin_user(db_session, username="nok_read_unlinked_admin")
    grant_permission(db_session, admin, "member.view")
    make_member(db_session, psn="NOK-READ-UL1", email="nokreadul1@example.com")
    make_member(db_session, psn="NOK-READ-UL2", email="nokreadul2@example.com")

    res = client.get("/api/members", params={"limit": 100}, headers=auth_headers(admin))
    assert res.status_code == 200
    body = res.json()
    assert body["total"] == 2
    assert all(item["conflicted"] is False for item in body["items"])


def test_member_detail_is_visible_and_flagged_when_actor_is_the_next_of_kin(
    client, db_session, seed_permissions
):
    own_member, admin = _admin_with_member(
        db_session, "nok_read_detail_a", "NOK-READ-DA", "nokreadda@example.com", "member.view"
    )
    target = make_member(db_session, psn="NOK-READ-DB", email="nokreaddb@example.com")
    _link_nok(db_session, own_member, target)

    res = client.get(f"/api/members/{target.id}", headers=auth_headers(admin))
    assert res.status_code == 200, res.text
    assert res.json()["conflicted"] is True


def test_member_detail_is_visible_and_flagged_when_target_lists_actor_as_next_of_kin(
    client, db_session, seed_permissions
):
    own_member, admin = _admin_with_member(
        db_session, "nok_read_detail_b", "NOK-READ-DC", "nokreaddc@example.com", "member.view"
    )
    target = make_member(db_session, psn="NOK-READ-DD", email="nokreaddd@example.com")
    _link_nok(db_session, target, own_member)

    res = client.get(f"/api/members/{target.id}", headers=auth_headers(admin))
    assert res.status_code == 200, res.text
    assert res.json()["conflicted"] is True


def test_member_detail_is_unflagged_for_own_and_unrelated_records(
    client, db_session, seed_permissions
):
    own_member, admin = _admin_with_member(
        db_session, "nok_read_detail_ok", "NOK-READ-DE", "nokreadde@example.com", "member.view"
    )
    unrelated = make_member(db_session, psn="NOK-READ-DF", email="nokreaddf@example.com")

    own_res = client.get(f"/api/members/{own_member.id}", headers=auth_headers(admin))
    assert own_res.status_code == 200, own_res.text
    assert own_res.json()["conflicted"] is False

    unrelated_res = client.get(f"/api/members/{unrelated.id}", headers=auth_headers(admin))
    assert unrelated_res.status_code == 200, unrelated_res.text
    assert unrelated_res.json()["conflicted"] is False


def test_member_detail_is_unflagged_after_relationship_is_removed(
    client, db_session, seed_permissions
):
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
    assert res.json()["conflicted"] is False


def test_member_detail_is_unflagged_when_conflict_flag_is_false(
    client, db_session, seed_permissions
):
    own_member, admin = _admin_with_member(
        db_session, "nok_read_detail_nf", "NOK-READ-DI", "nokreaddi@example.com", "member.view"
    )
    target = make_member(db_session, psn="NOK-READ-DJ", email="nokreaddj@example.com")
    _link_nok(db_session, own_member, target, conflict_of_interest=False)

    res = client.get(f"/api/members/{target.id}", headers=auth_headers(admin))
    assert res.status_code == 200, res.text
    assert res.json()["conflicted"] is False


# ---------------------------------------------------------------------------
# Loans / applications / repayments / deductions
# ---------------------------------------------------------------------------

def test_loan_reads_are_visible_and_flagged(client, db_session, seed_permissions):
    own_member, admin = _admin_with_member(
        db_session, "nok_read_loans", "NOK-READ-LO1", "nokreadlo1@example.com", "loan.view"
    )
    target = make_member(db_session, psn="NOK-READ-LO2", email="nokreadlo2@example.com")
    _link_nok(db_session, own_member, target)
    target_loan = _make_active_loan(db_session, target, "target")
    own_loan = _make_active_loan(db_session, own_member, "own")

    detail = client.get(f"/api/loans/{target_loan.id}", headers=auth_headers(admin))
    assert detail.status_code == 200, detail.text
    assert detail.json()["conflicted"] is True

    balance = client.get(f"/api/loans/member/{target.id}/balance", headers=auth_headers(admin))
    assert balance.status_code == 200, balance.text
    assert balance.json()["conflicted"] is True
    assert balance.json()["total_outstanding_balance"] == "1100.00"

    res = client.get("/api/loans", headers=auth_headers(admin))
    assert res.status_code == 200, res.text
    by_id = {loan["id"]: loan for loan in res.json()}
    assert by_id[str(own_loan.id)]["conflicted"] is False
    assert by_id[str(target_loan.id)]["conflicted"] is True

    # Filtering straight to the conflicted member works -- the record is
    # visible, only the actions are not.
    res = client.get(
        "/api/loans", params={"member_id": str(target.id)}, headers=auth_headers(admin)
    )
    assert res.status_code == 200
    assert [loan["conflicted"] for loan in res.json()] == [True]


def test_loan_application_reads_are_visible_and_flagged(client, db_session, seed_permissions):
    own_member, admin = _admin_with_member(
        db_session, "nok_read_apps", "NOK-READ-AP1", "nokreadap1@example.com", "loan.view"
    )
    target = make_member(db_session, psn="NOK-READ-AP2", email="nokreadap2@example.com")
    _link_nok(db_session, own_member, target)
    loan_type = make_loan_type(db_session, name="NOK Read Applications")
    target_app = _make_application(db_session, target, loan_type)
    own_app = _make_application(db_session, own_member, loan_type)

    detail = client.get(f"/api/loan-applications/{target_app.id}", headers=auth_headers(admin))
    assert detail.status_code == 200, detail.text
    assert detail.json()["conflicted"] is True

    res = client.get("/api/loan-applications", headers=auth_headers(admin))
    assert res.status_code == 200, res.text
    by_id = {app["id"]: app for app in res.json()}
    assert by_id[str(own_app.id)]["conflicted"] is False
    assert by_id[str(target_app.id)]["conflicted"] is True


def test_repayment_reads_are_visible_and_flagged(client, db_session, seed_permissions):
    own_member, admin = _admin_with_member(
        db_session, "nok_read_reps", "NOK-READ-RP1", "nokreadrp1@example.com", "repayment.view"
    )
    target = make_member(db_session, psn="NOK-READ-RP2", email="nokreadrp2@example.com")
    _link_nok(db_session, own_member, target)
    target_loan = _make_active_loan(db_session, target, "rep-target")
    target_repayment = _make_awaiting_repayment(db_session, target_loan, target)
    own_loan = _make_active_loan(db_session, own_member, "rep-own")
    own_repayment = _make_awaiting_repayment(db_session, own_loan, own_member)

    per_loan = client.get(f"/api/loans/{target_loan.id}/repayments", headers=auth_headers(admin))
    assert per_loan.status_code == 200, per_loan.text
    assert [repayment["conflicted"] for repayment in per_loan.json()] == [True]

    detail = client.get(f"/api/loan-repayments/{target_repayment.id}", headers=auth_headers(admin))
    assert detail.status_code == 200, detail.text
    assert detail.json()["conflicted"] is True

    res = client.get("/api/loan-repayments", headers=auth_headers(admin))
    assert res.status_code == 200, res.text
    by_id = {repayment["id"]: repayment for repayment in res.json()}
    assert by_id[str(own_repayment.id)]["conflicted"] is False
    assert by_id[str(target_repayment.id)]["conflicted"] is True


def test_deduction_reads_are_visible_and_flagged(client, db_session, seed_permissions):
    own_member, admin = _admin_with_member(
        db_session, "nok_read_deductions", "NOK-READ-DD1", "nokreaddd1@example.com",
        "deduction.view",
    )
    target = make_member(db_session, psn="NOK-READ-DD2", email="nokreaddd2@example.com")
    _link_nok(db_session, own_member, target)

    drafting_admin = make_admin_user(db_session, username="nok_read_deduction_writer")
    grant_permission(db_session, drafting_admin, "deduction.create", "deduction.view")
    for member in (own_member, target):
        res = client.post(
            "/api/payroll-deductions",
            headers=auth_headers(drafting_admin),
            json={
                "member_id": str(member.id),
                "deduction_month": "2026-11",
                "lines": [{"category": "monthly_contribution", "amount": "2000.00"}],
            },
        )
        assert res.status_code == 201, res.text

    schedule = client.get(
        "/api/payroll-deductions/schedule", params={"month": "2026-11"}, headers=auth_headers(admin)
    )
    assert schedule.status_code == 200, schedule.text
    body = schedule.json()
    assert {record["member_psn"]: record["conflicted"] for record in body["records"]} == {
        own_member.psn: False,
        target.psn: True,
    }
    # The month still totals every member, including the conflicted one --
    # payroll reconciles against the whole schedule, not a censored copy.
    assert body["totals"]["contribution_total"] == "4000.00"

    ledger = client.get("/api/payroll-deductions", params={"month": "2026-11"}, headers=auth_headers(admin))
    assert ledger.status_code == 200, ledger.text
    assert sorted(record["conflicted"] for record in ledger.json()) == [False, True]

    target_record = next(r for r in ledger.json() if r["member_psn"] == target.psn)
    detail = client.get(f"/api/payroll-deductions/{target_record['id']}", headers=auth_headers(admin))
    assert detail.status_code == 200, detail.text
    assert detail.json()["conflicted"] is True


# ---------------------------------------------------------------------------
# The action boundary is unchanged
# ---------------------------------------------------------------------------

def test_a_conflicted_officer_can_read_but_still_not_edit(client, db_session, seed_permissions):
    own_member, admin = _admin_with_member(
        db_session, "nok_read_boundary", "NOK-READ-BD1", "nokreadbd1@example.com",
        "member.view", "member.update",
    )
    target = make_member(db_session, psn="NOK-READ-BD2", email="nokreadbd2@example.com")
    _link_nok(db_session, own_member, target)

    read = client.get(f"/api/members/{target.id}", headers=auth_headers(admin))
    assert read.status_code == 200, read.text
    assert read.json()["conflicted"] is True

    write = client.put(
        f"/api/members/{target.id}",
        headers=auth_headers(admin),
        json={"name": "Renamed By Conflicted Officer"},
    )
    assert write.status_code == 409, write.text
    assert write.json()["detail"]["error"] == "member_conflict"


# ---------------------------------------------------------------------------
# Self-service / audit
# ---------------------------------------------------------------------------

def test_member_self_service_reads_are_unaffected(client, db_session, seed_permissions):
    """The conflicted admin's next of kin keeps full access to their own
    record and financial data -- and their own rows are never flagged."""
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

    own_record = client.get(f"/api/members/{target.id}", headers=headers)
    assert own_record.status_code == 200
    assert own_record.json()["conflicted"] is False

    loans = client.get("/api/loans", headers=headers)
    assert loans.status_code == 200
    assert all(loan["conflicted"] is False for loan in loans.json())

    assert client.get(f"/api/loans/{loan.id}", headers=headers).status_code == 200
    per_loan = client.get(f"/api/loans/{loan.id}/repayments", headers=headers)
    assert per_loan.status_code == 200
    assert all(repayment["conflicted"] is False for repayment in per_loan.json())
    applications = client.get("/api/loan-applications", headers=headers)
    assert applications.status_code == 200
    assert all(app["conflicted"] is False for app in applications.json())
    assert client.get(f"/api/loan-applications/{application.id}", headers=headers).status_code == 200
    detail = client.get(f"/api/loan-repayments/{repayment.id}", headers=headers)
    assert detail.status_code == 200
    assert detail.json()["conflicted"] is False


def test_conflicted_view_is_audit_logged(client, db_session, seed_permissions):
    from app import models

    own_member, admin = _admin_with_member(
        db_session, "nok_read_audit", "NOK-READ-AU1", "nokreadau1@example.com", "member.view"
    )
    target = make_member(db_session, psn="NOK-READ-AU2", email="nokreadau2@example.com")
    _link_nok(db_session, own_member, target)

    res = client.get(f"/api/members/{target.id}", headers=auth_headers(admin))
    assert res.status_code == 200, res.text

    event = (
        db_session.query(models.AuditEvent)
        .filter(
            models.AuditEvent.event_type == "conflict_of_interest.viewed",
            models.AuditEvent.entity_type == "member",
            models.AuditEvent.entity_id == str(target.id),
        )
        .first()
    )
    assert event is not None
    assert event.action == "view"
    assert event.actor_user_id == admin.id
    assert event.new_values == {"conflicted_records": 1}
    assert "conflict-of-interest" in (event.reason or "")
    assert "blocked" in (event.reason or "").lower()


def test_an_unflagged_view_writes_no_conflict_audit_event(client, db_session, seed_permissions):
    from app import models

    own_member, admin = _admin_with_member(
        db_session, "nok_read_audit_clean", "NOK-READ-AC1", "nokreadac1@example.com", "member.view"
    )
    unrelated = make_member(db_session, psn="NOK-READ-AC2", email="nokreadac2@example.com")

    res = client.get(f"/api/members/{unrelated.id}", headers=auth_headers(admin))
    assert res.status_code == 200, res.text

    event = (
        db_session.query(models.AuditEvent)
        .filter(
            models.AuditEvent.event_type == "conflict_of_interest.viewed",
            models.AuditEvent.actor_user_id == admin.id,
        )
        .first()
    )
    assert event is None
