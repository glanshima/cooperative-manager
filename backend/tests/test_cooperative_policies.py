"""Cooperative-level contribution and loan-default policy (2026-11).

The floor a member's contribution must meet, the figure the add-member
form starts at, and the loan-default charge and grace period all live on
the cooperative's single settings row. Nothing here is a constant in code.
"""
from decimal import Decimal

from app import models
from tests.conftest import (
    auth_headers,
    make_admin_user,
    make_member,
    make_member_user,
    make_settings,
)


def _put(client, admin, **payload):
    return client.put("/api/settings", headers=auth_headers(admin), json=payload)


def _bootstrap(client, admin, member, amount):
    return client.put(
        f"/api/members/{member.id}",
        headers=auth_headers(admin),
        json={"monthly_contribution_amount": amount},
    )


def test_the_floor_is_read_from_the_settings_row(client, db_session):
    make_settings(
        db_session,
        minimum_monthly_contribution=Decimal("6000"),
        default_monthly_contribution=Decimal("6000"),
    )
    admin = make_admin_user(db_session, username="policy_floor", super_admin=True)
    member = make_member(db_session, psn="PSN-POL-1", email="pol1@example.com")

    below = _bootstrap(client, admin, member, "5500.00")
    assert below.status_code == 422, below.text
    assert "6,000.00" in below.json()["detail"]

    assert _bootstrap(client, admin, member, "6000.00").status_code == 200


def test_raising_the_floor_changes_what_is_accepted(client, db_session):
    make_settings(
        db_session,
        minimum_monthly_contribution=Decimal("5000"),
        default_monthly_contribution=Decimal("5000"),
    )
    admin = make_admin_user(db_session, username="policy_raise", super_admin=True)

    saved = _put(
        client,
        admin,
        minimum_monthly_contribution="7000.00",
        default_monthly_contribution="7000.00",
    )
    assert saved.status_code == 200, saved.text
    assert Decimal(saved.json()["minimum_monthly_contribution"]) == Decimal("7000.00")

    member = make_member(db_session, psn="PSN-POL-2", email="pol2@example.com")
    assert _bootstrap(client, admin, member, "6500.00").status_code == 422


def test_a_default_below_the_minimum_is_refused(client, db_session):
    make_settings(
        db_session,
        minimum_monthly_contribution=Decimal("5000"),
        default_monthly_contribution=Decimal("5000"),
    )
    admin = make_admin_user(db_session, username="policy_default", super_admin=True)

    res = _put(client, admin, default_monthly_contribution="3000.00")
    assert res.status_code == 400, res.text
    assert "below the minimum" in res.json()["detail"]

    db_session.expire_all()
    settings = db_session.query(models.Settings).first()
    assert settings.default_monthly_contribution == Decimal("5000.00")


def test_grace_days_only_apply_in_day_mode(client, db_session):
    make_settings(db_session, loan_default_grace_days=0)
    admin = make_admin_user(db_session, username="policy_grace", super_admin=True)

    days = _put(client, admin, loan_default_grace_mode="days", loan_default_grace_days=14)
    assert days.status_code == 200, days.text
    assert days.json()["loan_default_grace_mode"] == "days"
    assert days.json()["loan_default_grace_days"] == 14

    stale = _put(client, admin, loan_default_grace_mode="next_payroll")
    assert stale.status_code == 400, stale.text
    assert "counted in days" in stale.json()["detail"]

    cleared = _put(
        client, admin, loan_default_grace_mode="next_payroll", loan_default_grace_days=0
    )
    assert cleared.status_code == 200, cleared.text


def test_the_default_charge_is_a_percentage(client, db_session):
    make_settings(db_session)
    admin = make_admin_user(db_session, username="policy_charge", super_admin=True)

    assert _put(client, admin, loan_default_charge_pct="150").status_code == 422
    assert _put(client, admin, loan_default_charge_pct="-1").status_code == 422

    saved = _put(client, admin, loan_default_charge_pct="10")
    assert saved.status_code == 200, saved.text
    assert Decimal(saved.json()["loan_default_charge_pct"]) == Decimal("10")


def test_an_approved_change_must_still_meet_the_current_floor(client, db_session):
    """The floor may move while a request waits, so approval re-checks it."""
    make_settings(
        db_session,
        minimum_monthly_contribution=Decimal("5000"),
        default_monthly_contribution=Decimal("5000"),
    )
    admin = make_admin_user(db_session, username="policy_approve", super_admin=True)
    member = make_member(db_session, psn="PSN-POL-3", email="pol3@example.com")
    user = make_member_user(db_session, member)
    assert _bootstrap(client, admin, member, "5000.00").status_code == 200

    raised = client.post(
        "/api/members/me/contribution-change-requests",
        headers=auth_headers(user),
        json={"requested_amount": "5500.00", "reason": "Salary review"},
    )
    assert raised.status_code == 201, raised.text

    db_session.query(models.Settings).one().minimum_monthly_contribution = Decimal("6000")
    db_session.commit()

    decide = client.post(
        f"/api/contribution-change-requests/{raised.json()['id']}/approve",
        headers=auth_headers(admin),
        json={},
    )
    assert decide.status_code == 422, decide.text

    rejected = client.post(
        f"/api/contribution-change-requests/{raised.json()['id']}/reject",
        headers=auth_headers(admin),
        json={"reason": "Below the new floor"},
    )
    assert rejected.status_code == 200, rejected.text
