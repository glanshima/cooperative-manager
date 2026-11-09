"""Monthly contribution amounts and the change-request flow (2026-11).

The contract these tests pin down:

  - The stored amount is what payroll deducts. An officer records it ONCE
    (bootstrap, while it is unset, from the current month); every later
    change needs a request that a second officer decides.
  - The cooperative minimum (5000) is enforced on both paths.
  - Only financial members have a contribution -- a non-financial member
    cannot bootstrap one, apply for one, or have one approved into place.
  - Approval is never retroactive: it takes effect from the first of next
    month, so the month already being entered keeps its old figure and
    confirmed deduction lines (the savings balance) are untouched.
  - One pending request per member; a decided request cannot be decided
    again; rejecting needs a reason.
  - Reading the review queue follows the conflict-of-interest READ policy
    (visible + flagged); deciding it stays blocked for a conflicted
    officer. A member applying about their OWN record is not a conflict.
  - The Members module toggle gates the officer surface, not the member's
    own self-service endpoints.
"""
from datetime import date
from decimal import Decimal

from app import contributions as contribution_rules
from app import models
from tests.conftest import (
    auth_headers,
    grant_permission,
    make_admin_user,
    make_member,
    make_member_user,
)

MINIMUM = Decimal("5000")


def _this_month_start() -> date:
    return date.today().replace(day=1)


def _member_amount(db_session, member):
    db_session.expire_all()
    return db_session.query(models.Member).filter(models.Member.id == member.id).one()


def _bootstrap(client, admin, member, amount="5000.00"):
    return client.put(
        f"/api/members/{member.id}",
        headers=auth_headers(admin),
        json={"monthly_contribution_amount": amount},
    )


def _apply(client, user, amount="8000.00", reason="Salary increase"):
    return client.post(
        "/api/members/me/contribution-change-requests",
        headers=auth_headers(user),
        json={"requested_amount": amount, "reason": reason},
    )


def _link_nok(db_session, member, related_member):
    relationship = models.MemberRelationship(
        member_id=member.id,
        related_member_id=related_member.id,
        conflict_of_interest=True,
        status=models.RelationshipStatus.ACTIVE,
    )
    db_session.add(relationship)
    db_session.commit()
    return relationship


# ---------------------------------------------------------------------------
# Bootstrap
# ---------------------------------------------------------------------------

def test_officer_bootstraps_the_amount_once_from_the_current_month(client, db_session):
    admin = make_admin_user(db_session, username="contrib_boot", super_admin=True)
    member = make_member(db_session, psn="PSN-CON-1", email="con1@example.com")

    res = _bootstrap(client, admin, member)
    assert res.status_code == 200, res.text
    body = res.json()
    assert Decimal(body["monthly_contribution_amount"]) == MINIMUM
    assert body["contribution_effective_from"] == _this_month_start().isoformat()

    again = _bootstrap(client, admin, member, amount="9000.00")
    assert again.status_code == 409, again.text
    assert "change request" in again.json()["detail"]
    assert Decimal(_member_amount(db_session, member).monthly_contribution_amount) == MINIMUM


def test_bootstrap_below_the_minimum_is_rejected(client, db_session):
    admin = make_admin_user(db_session, username="contrib_min", super_admin=True)
    member = make_member(db_session, psn="PSN-CON-2", email="con2@example.com")

    res = _bootstrap(client, admin, member, amount="4999.99")
    assert res.status_code == 422, res.text
    assert _member_amount(db_session, member).monthly_contribution_amount is None


def test_the_amount_cannot_be_cleared_through_an_edit(client, db_session):
    admin = make_admin_user(db_session, username="contrib_clear", super_admin=True)
    member = make_member(db_session, psn="PSN-CON-3", email="con3@example.com")
    assert _bootstrap(client, admin, member).status_code == 200

    res = client.put(
        f"/api/members/{member.id}",
        headers=auth_headers(admin),
        json={"monthly_contribution_amount": None},
    )
    assert res.status_code == 422, res.text
    assert Decimal(_member_amount(db_session, member).monthly_contribution_amount) == MINIMUM


def test_non_financial_members_cannot_be_given_a_contribution(client, db_session):
    admin = make_admin_user(db_session, username="contrib_nonfin", super_admin=True)
    member = make_member(
        db_session,
        psn="PSN-CON-4",
        email="con4@example.com",
        status=models.MemberStatus.NON_FINANCIAL,
    )

    res = _bootstrap(client, admin, member)
    assert res.status_code == 400, res.text
    assert "financial members" in res.json()["detail"]

    # Reactivating and recording the amount in the SAME edit is allowed:
    # the rule is judged against the status the edit is about to store.
    res = client.put(
        f"/api/members/{member.id}",
        headers=auth_headers(admin),
        json={"status": "financial", "monthly_contribution_amount": "6000.00"},
    )
    assert res.status_code == 200, res.text
    assert Decimal(res.json()["monthly_contribution_amount"]) == Decimal("6000.00")


def test_a_new_member_can_be_created_with_their_initial_amount(client, db_session):
    admin = make_admin_user(db_session, username="contrib_create", super_admin=True)

    res = client.post(
        "/api/members",
        headers=auth_headers(admin),
        json={
            "psn": "PSN-CON-5",
            "name": "Created With Amount",
            "next_of_kin_is_member": False,
            "monthly_contribution_amount": "5000.00",
        },
    )
    assert res.status_code == 201, res.text
    assert res.json()["contribution_effective_from"] == _this_month_start().isoformat()

    res = client.post(
        "/api/members",
        headers=auth_headers(admin),
        json={
            "psn": "PSN-CON-6",
            "name": "Non Financial With Amount",
            "next_of_kin_is_member": False,
            "status": "non_financial",
            "monthly_contribution_amount": "5000.00",
        },
    )
    assert res.status_code == 400, res.text


# ---------------------------------------------------------------------------
# Apply -> decide
# ---------------------------------------------------------------------------

def test_member_applies_and_approval_takes_effect_next_month(client, db_session):
    admin = make_admin_user(db_session, username="contrib_approver", super_admin=True)
    member = make_member(db_session, psn="PSN-CON-7", email="con7@example.com")
    user = make_member_user(db_session, member)
    assert _bootstrap(client, admin, member).status_code == 200

    res = _apply(client, user)
    assert res.status_code == 201, res.text
    request_body = res.json()
    assert request_body["status"] == "pending"
    assert Decimal(request_body["current_amount"]) == MINIMUM
    assert Decimal(request_body["requested_amount"]) == Decimal("8000.00")
    assert request_body["member_psn"] == "PSN-CON-7"
    assert request_body["effective_from"] is None

    # Still the old figure until someone decides it.
    assert Decimal(_member_amount(db_session, member).monthly_contribution_amount) == MINIMUM

    res = client.post(
        f"/api/contribution-change-requests/{request_body['id']}/approve",
        headers=auth_headers(admin),
        json={},
    )
    assert res.status_code == 200, res.text
    decided = res.json()
    assert decided["status"] == "approved"
    expected_month = contribution_rules.next_month_start(date.today())
    assert decided["effective_from"] == expected_month.isoformat()

    stored = _member_amount(db_session, member)
    assert Decimal(stored.monthly_contribution_amount) == Decimal("8000.00")
    assert stored.contribution_effective_from == expected_month
    # The month being entered right now keeps the old amount.
    assert contribution_rules.amount_for_month(db_session, stored, _this_month_start()) == MINIMUM
    assert contribution_rules.amount_for_month(db_session, stored, expected_month) == Decimal("8000.00")


def test_successive_changes_still_price_every_month_correctly(client, db_session):
    """Both approvals land in the same calendar month, so both take effect
    on the same date: the later decision supersedes the earlier one, and
    the month before them keeps the figure that was actually in force."""
    admin = make_admin_user(db_session, username="contrib_successive", super_admin=True)
    member = make_member(db_session, psn="PSN-CON-24", email="con24@example.com")
    user = make_member_user(db_session, member)
    assert _bootstrap(client, admin, member).status_code == 200

    first = _apply(client, user, amount="8000.00").json()
    client.post(
        f"/api/contribution-change-requests/{first['id']}/approve",
        headers=auth_headers(admin),
        json={},
    )
    second = _apply(client, user, amount="10000.00").json()
    assert Decimal(second["current_amount"]) == Decimal("8000.00")
    res = client.post(
        f"/api/contribution-change-requests/{second['id']}/approve",
        headers=auth_headers(admin),
        json={},
    )
    assert res.status_code == 200, res.text

    stored = _member_amount(db_session, member)
    effective = contribution_rules.next_month_start(date.today())
    assert Decimal(stored.monthly_contribution_amount) == Decimal("10000.00")
    assert contribution_rules.amount_for_month(db_session, stored, _this_month_start()) == MINIMUM
    assert contribution_rules.amount_for_month(db_session, stored, effective) == Decimal("10000.00")


def test_bootstrapping_with_a_request_pending_refreshes_its_snapshot(client, db_session):
    admin = make_admin_user(db_session, username="contrib_boot_pending", super_admin=True)
    member = make_member(db_session, psn="PSN-CON-25", email="con25@example.com")
    user = make_member_user(db_session, member)

    request_id = _apply(client, user).json()["id"]
    assert _bootstrap(client, admin, member).status_code == 200

    pending = (
        db_session.query(models.ContributionChangeRequest)
        .filter(models.ContributionChangeRequest.id == request_id)
        .one()
    )
    assert Decimal(pending.current_amount) == MINIMUM

    client.post(
        f"/api/contribution-change-requests/{request_id}/approve",
        headers=auth_headers(admin),
        json={},
    )
    stored = _member_amount(db_session, member)
    assert contribution_rules.amount_for_month(db_session, stored, _this_month_start()) == MINIMUM


def test_only_one_request_can_be_pending_per_member(client, db_session):
    member = make_member(db_session, psn="PSN-CON-8", email="con8@example.com")
    user = make_member_user(db_session, member)

    assert _apply(client, user).status_code == 201
    second = _apply(client, user, amount="9000.00")
    assert second.status_code == 409, second.text
    assert "awaiting a decision" in second.json()["detail"]


def test_applying_for_the_amount_already_in_place_is_rejected(client, db_session):
    admin = make_admin_user(db_session, username="contrib_same", super_admin=True)
    member = make_member(db_session, psn="PSN-CON-9", email="con9@example.com")
    user = make_member_user(db_session, member)
    assert _bootstrap(client, admin, member).status_code == 200

    res = _apply(client, user, amount="5000.00")
    assert res.status_code == 400, res.text
    assert "already" in res.json()["detail"]


def test_a_member_with_no_amount_on_file_can_still_apply(client, db_session):
    member = make_member(db_session, psn="PSN-CON-10", email="con10@example.com")
    user = make_member_user(db_session, member)

    res = _apply(client, user)
    assert res.status_code == 201, res.text
    assert res.json()["current_amount"] is None


def test_non_financial_members_cannot_apply(client, db_session):
    member = make_member(
        db_session,
        psn="PSN-CON-11",
        email="con11@example.com",
        status=models.MemberStatus.NON_FINANCIAL,
    )
    user = make_member_user(db_session, member)

    res = _apply(client, user)
    assert res.status_code == 400, res.text
    assert "financial members" in res.json()["detail"]


def test_below_minimum_applications_are_rejected(client, db_session):
    member = make_member(db_session, psn="PSN-CON-12", email="con12@example.com")
    user = make_member_user(db_session, member)

    assert _apply(client, user, amount="1000.00").status_code == 422
    assert _apply(client, user, reason="   ").status_code == 422


def test_reject_needs_a_reason_and_leaves_the_amount_alone(client, db_session):
    admin = make_admin_user(db_session, username="contrib_rejector", super_admin=True)
    member = make_member(db_session, psn="PSN-CON-13", email="con13@example.com")
    user = make_member_user(db_session, member)
    assert _bootstrap(client, admin, member).status_code == 200
    request_id = _apply(client, user).json()["id"]

    res = client.post(
        f"/api/contribution-change-requests/{request_id}/reject",
        headers=auth_headers(admin),
        json={"reason": "  "},
    )
    assert res.status_code == 422, res.text

    res = client.post(
        f"/api/contribution-change-requests/{request_id}/reject",
        headers=auth_headers(admin),
        json={"reason": "Payroll cannot absorb an increase this quarter"},
    )
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "rejected"
    assert res.json()["review_reason"] == "Payroll cannot absorb an increase this quarter"

    stored = _member_amount(db_session, member)
    assert Decimal(stored.monthly_contribution_amount) == MINIMUM
    assert stored.contribution_effective_from == _this_month_start()


def test_a_decided_request_cannot_be_decided_again(client, db_session):
    admin = make_admin_user(db_session, username="contrib_twice", super_admin=True)
    member = make_member(db_session, psn="PSN-CON-14", email="con14@example.com")
    user = make_member_user(db_session, member)
    request_id = _apply(client, user).json()["id"]

    path = f"/api/contribution-change-requests/{request_id}/approve"
    assert client.post(path, headers=auth_headers(admin), json={}).status_code == 200
    again = client.post(path, headers=auth_headers(admin), json={})
    assert again.status_code == 409, again.text
    assert "already been approved" in again.json()["detail"]


def test_approving_after_the_member_left_is_refused(client, db_session):
    admin = make_admin_user(db_session, username="contrib_exited", super_admin=True)
    member = make_member(db_session, psn="PSN-CON-15", email="con15@example.com")
    user = make_member_user(db_session, member)
    request_id = _apply(client, user).json()["id"]

    member.status = models.MemberStatus.NON_FINANCIAL
    member.membership_exit_date = date.today()
    db_session.commit()

    res = client.post(
        f"/api/contribution-change-requests/{request_id}/approve",
        headers=auth_headers(admin),
        json={},
    )
    assert res.status_code == 400, res.text
    assert _member_amount(db_session, member).monthly_contribution_amount is None

    # Rejecting it is still the right way to close it out.
    res = client.post(
        f"/api/contribution-change-requests/{request_id}/reject",
        headers=auth_headers(admin),
        json={"reason": "Member has left the cooperative"},
    )
    assert res.status_code == 200, res.text


def test_an_officer_can_raise_a_request_for_a_member_without_a_login(client, db_session, seed_permissions):
    officer = make_admin_user(db_session, username="contrib_proxy")
    grant_permission(db_session, officer, "savings.request_change")
    member = make_member(db_session, psn="PSN-CON-16", email="con16@example.com")

    res = client.post(
        "/api/contribution-change-requests",
        headers=auth_headers(officer),
        json={
            "member_id": str(member.id),
            "requested_amount": "7500.00",
            "reason": "Member asked at the office",
        },
    )
    assert res.status_code == 201, res.text
    assert res.json()["member_psn"] == "PSN-CON-16"
    assert res.json()["requested_by_user_id"] == str(officer.id)


# ---------------------------------------------------------------------------
# Permissions, conflict of interest, module toggle, audit
# ---------------------------------------------------------------------------

def test_the_review_surface_needs_its_own_permissions(client, db_session, seed_permissions):
    member = make_member(db_session, psn="PSN-CON-17", email="con17@example.com")
    user = make_member_user(db_session, member)
    request_id = _apply(client, user).json()["id"]

    viewer = make_admin_user(db_session, username="contrib_viewer")
    grant_permission(db_session, viewer, "savings.view")
    res = client.get("/api/contribution-change-requests", headers=auth_headers(viewer))
    assert res.status_code == 200, res.text
    assert len(res.json()) == 1

    res = client.post(
        f"/api/contribution-change-requests/{request_id}/approve",
        headers=auth_headers(viewer),
        json={},
    )
    assert res.status_code == 403, res.text

    # A member cannot reach the officer queue at all.
    res = client.get("/api/contribution-change-requests", headers=auth_headers(user))
    assert res.status_code == 403, res.text


def test_a_member_only_sees_their_own_requests(client, db_session):
    mine = make_member(db_session, psn="PSN-CON-18", email="con18@example.com")
    other = make_member(db_session, psn="PSN-CON-19", email="con19@example.com")
    my_user = make_member_user(db_session, mine)
    other_user = make_member_user(db_session, other)
    _apply(client, other_user)

    res = client.get(
        "/api/members/me/contribution-change-requests", headers=auth_headers(my_user)
    )
    assert res.status_code == 200, res.text
    assert res.json() == []

    _apply(client, my_user)
    res = client.get(
        "/api/members/me/contribution-change-requests", headers=auth_headers(my_user)
    )
    assert len(res.json()) == 1
    assert res.json()[0]["member_id"] == str(mine.id)
    assert res.json()[0]["conflicted"] is False


def test_a_conflicted_officer_reads_the_queue_but_cannot_decide_it(client, db_session):
    decider = make_admin_user(db_session, username="contrib_conflicted", super_admin=True)
    linked = make_member(db_session, psn="PSN-CON-20", email="con20@example.com")
    decider.member_id = linked.id
    db_session.commit()

    member = make_member(db_session, psn="PSN-CON-21", email="con21@example.com")
    user = make_member_user(db_session, member)
    _link_nok(db_session, member, linked)
    request_id = _apply(client, user).json()["id"]

    res = client.get("/api/contribution-change-requests", headers=auth_headers(decider))
    assert res.status_code == 200, res.text
    assert res.json()[0]["conflicted"] is True

    res = client.post(
        f"/api/contribution-change-requests/{request_id}/approve",
        headers=auth_headers(decider),
        json={},
    )
    assert res.status_code == 409, res.text
    assert res.json()["detail"]["error"] == "member_conflict"
    assert _member_amount(db_session, member).monthly_contribution_amount is None


def test_the_members_toggle_gates_officers_not_self_service(client, db_session):
    admin = make_admin_user(db_session, username="contrib_toggle", super_admin=True)
    member = make_member(db_session, psn="PSN-CON-22", email="con22@example.com")
    user = make_member_user(db_session, member)

    db_session.add(models.Settings(members_module_enabled=False))
    db_session.commit()

    res = client.get("/api/contribution-change-requests", headers=auth_headers(admin))
    assert res.status_code == 403, res.text

    # The member's own dashboard keeps working: this is self-service, not
    # the module's administration surface (same exemption as GET /me).
    assert _apply(client, user).status_code == 201
    res = client.get(
        "/api/members/me/contribution-change-requests", headers=auth_headers(user)
    )
    assert res.status_code == 200, res.text


def test_requests_and_decisions_are_audit_logged(client, db_session):
    admin = make_admin_user(db_session, username="contrib_audit", super_admin=True)
    member = make_member(db_session, psn="PSN-CON-23", email="con23@example.com")
    user = make_member_user(db_session, member)
    request_id = _apply(client, user).json()["id"]
    client.post(
        f"/api/contribution-change-requests/{request_id}/approve",
        headers=auth_headers(admin),
        json={"reason": "Approved at the monthly meeting"},
    )

    events = (
        db_session.query(models.AuditEvent)
        .filter(models.AuditEvent.entity_id == request_id)
        .order_by(models.AuditEvent.timestamp)
        .all()
    )
    assert [event.event_type for event in events] == [
        "contribution_change.requested",
        "contribution_change.approved",
    ]
    approved = events[-1]
    assert approved.action == "approve"
    assert approved.actor_user_id == admin.id
    assert approved.new_values["member_previous_amount"] is None
    assert approved.new_values["member_new_amount"] == "8000.00"
    assert approved.new_values["effective_from"] == (
        contribution_rules.next_month_start(date.today()).isoformat()
    )