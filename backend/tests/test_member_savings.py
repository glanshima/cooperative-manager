"""GET /api/members/me/savings -- the figure on a member's dashboard.

Savings has no separate ledger here: it is the sum of the monthly
contribution lines payroll actually deducted, so this endpoint is a read
over deductions and inherits every rule of that lifecycle.

  - confirmed records only. A draft or a submission is intent, not money
    received; a void corrects money that was wrongly taken.
  - the monthly contribution line only. Loan repayments and 'other' lines
    are deductions too, but they are not savings.
  - months_contributed counts distinct confirmed months so the card can say
    "across 13 months" without a second request.
  - it stops at the caller's own member record and needs no permission code
    (same self-service exemption as the rest of /me), which is why it is not
    a field on MemberOut: that schema is serialized for every row of the
    members list, where this SUM would be paid a hundred times per page to
    serve nobody who reads it.
"""
from decimal import Decimal

from app import models
from tests.conftest import (
    auth_headers,
    make_admin_user,
    make_member,
    make_member_user,
)


def _create(client, admin, member, *, month, contribution="5000.00", other=None):
    lines = [{"category": "monthly_contribution", "amount": contribution}]
    if other:
        lines.append({"category": "other", "label": "Welfare", "amount": other})
    res = client.post(
        "/api/payroll-deductions",
        headers=auth_headers(admin),
        json={"member_id": str(member.id), "deduction_month": month, "lines": lines},
    )
    assert res.status_code == 201, res.text
    return res.json()["id"]


def _confirmed(client, admin, member, *, month, contribution="5000.00", other=None):
    deduction_id = _create(
        client, admin, member, month=month, contribution=contribution, other=other
    )
    for action in ("submit", "confirm"):
        res = client.post(
            f"/api/payroll-deductions/{deduction_id}/{action}", headers=auth_headers(admin)
        )
        assert res.status_code == 200, res.text
    return deduction_id


def _savings(client, user):
    return client.get("/api/members/me/savings", headers=auth_headers(user))


def test_the_balance_is_every_confirmed_contribution(client, db_session):
    admin = make_admin_user(db_session, username="sav_admin", super_admin=True)
    member = make_member(db_session, psn="PSN-SAV-1", email="sav1@example.com")
    user = make_member_user(db_session, member)

    _confirmed(client, admin, member, month="2026-09")
    _confirmed(client, admin, member, month="2026-10", other="500.00")
    _confirmed(client, admin, member, month="2026-11", contribution="6000.00")

    res = _savings(client, user)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["member_id"] == str(member.id)
    # 16000, not 16500: the welfare line left the paycheck but is not savings.
    assert Decimal(body["savings_balance"]) == Decimal("16000.00")
    assert body["months_contributed"] == 3


def test_nothing_unconfirmed_counts_as_savings(client, db_session):
    admin = make_admin_user(db_session, username="sav_draft", super_admin=True)
    member = make_member(db_session, psn="PSN-SAV-2", email="sav2@example.com")
    user = make_member_user(db_session, member)

    assert Decimal("0") == Decimal(_savings(client, user).json()["savings_balance"])

    _create(client, admin, member, month="2026-11")
    body = _savings(client, user).json()
    assert (Decimal(body["savings_balance"]), body["months_contributed"]) == (Decimal("0"), 0)

    submitted = _create(client, admin, member, month="2026-10")
    res = client.post(f"/api/payroll-deductions/{submitted}/submit", headers=auth_headers(admin))
    assert res.status_code == 200, res.text
    body = _savings(client, user).json()
    assert (Decimal(body["savings_balance"]), body["months_contributed"]) == (Decimal("0"), 0)

    res = client.post(f"/api/payroll-deductions/{submitted}/confirm", headers=auth_headers(admin))
    assert res.status_code == 200, res.text
    body = _savings(client, user).json()
    assert (Decimal(body["savings_balance"]), body["months_contributed"]) == (Decimal("5000.00"), 1)


def test_a_void_takes_the_month_back_out(client, db_session):
    admin = make_admin_user(db_session, username="sav_void", super_admin=True)
    member = make_member(db_session, psn="PSN-SAV-3", email="sav3@example.com")
    user = make_member_user(db_session, member)

    _confirmed(client, admin, member, month="2026-10")
    mistaken = _confirmed(client, admin, member, month="2026-11")

    res = client.post(
        f"/api/payroll-deductions/{mistaken}/void",
        headers=auth_headers(admin),
        json={"reason": "deducted twice"},
    )
    assert res.status_code == 200, res.text

    body = _savings(client, user).json()
    assert (Decimal(body["savings_balance"]), body["months_contributed"]) == (Decimal("5000.00"), 1)


def test_a_member_only_ever_sees_their_own_balance(client, db_session):
    admin = make_admin_user(db_session, username="sav_isolation", super_admin=True)
    mine = make_member(db_session, psn="PSN-SAV-4", email="sav4@example.com")
    other = make_member(db_session, psn="PSN-SAV-5", email="sav5@example.com")
    my_user = make_member_user(db_session, mine)
    other_user = make_member_user(db_session, other)

    _confirmed(client, admin, mine, month="2026-11", contribution="5000.00")
    _confirmed(client, admin, other, month="2026-11", contribution="9000.00")

    assert Decimal(_savings(client, my_user).json()["savings_balance"]) == Decimal("5000.00")
    assert Decimal(_savings(client, other_user).json()["savings_balance"]) == Decimal("9000.00")
    assert _savings(client, my_user).json()["member_id"] == str(mine.id)


def test_officers_have_no_savings_balance(client, db_session):
    admin = make_admin_user(db_session, username="sav_officer", super_admin=True)

    res = _savings(client, admin)
    assert res.status_code == 403, res.text


def test_the_members_toggle_does_not_close_the_dashboard(client, db_session):
    admin = make_admin_user(db_session, username="sav_toggle", super_admin=True)
    member = make_member(db_session, psn="PSN-SAV-7", email="sav7@example.com")
    user = make_member_user(db_session, member)
    _confirmed(client, admin, member, month="2026-11")

    db_session.add(models.Settings(members_module_enabled=False))
    db_session.commit()

    res = _savings(client, user)
    assert res.status_code == 200, res.text
    assert Decimal(res.json()["savings_balance"]) == Decimal("5000.00")
