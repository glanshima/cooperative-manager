"""GET /api/members/me/deductions -- the "this month" card on a member's
dashboard.

The card must never conflate the three things payroll can take: the
monthly contribution (savings), loan repayments (including arrears), and
anything else. It also has to say whether the money actually left the
paycheck -- a draft is intent, only confirmed is money.
"""
from datetime import date
from decimal import Decimal

from app import models
from tests.conftest import (
    auth_headers,
    make_admin_user,
    make_loan_type,
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


def _add_loan_lines(db_session, deduction_id, member, *, repayment="1000.00", arrears="250.00"):
    loan_type = make_loan_type(db_session, name=f"Normal-{deduction_id[:8]}")
    loan = models.Loan(
        member_id=member.id,
        loan_type_id=loan_type.id,
        principal=Decimal("10000.00"),
        interest_amount=Decimal("0"),
        net_disbursed=Decimal("10000.00"),
        total_repayable=Decimal("10000.00"),
        monthly_installment=Decimal("1000.00"),
        disbursement_date=date(2026, 1, 5),
        expected_end_date=date(2026, 11, 5),
    )
    db_session.add(loan)
    db_session.commit()
    for category, amount in (("loan_repayment", repayment), ("loan_arrears", arrears)):
        db_session.add(
            models.PayrollDeductionLine(
                deduction_id=deduction_id,
                category=models.PayrollDeductionLineCategory(category),
                loan_id=loan.id,
                amount=Decimal(amount),
            )
        )
    db_session.commit()
    return loan


def _mine(client, user, month=None):
    params = {"month": month} if month else {}
    return client.get("/api/members/me/deductions", headers=auth_headers(user), params=params)


def test_the_month_splits_contribution_loan_and_other(client, db_session):
    admin = make_admin_user(db_session, username="ded_split", super_admin=True)
    member = make_member(db_session, psn="PSN-DED-1", email="ded1@example.com")
    user = make_member_user(db_session, member)

    month = date.today().strftime("%Y-%m")
    deduction_id = _create(client, admin, member, month=month, contribution="5000.00", other="500.00")
    _add_loan_lines(db_session, deduction_id, member)

    body = _mine(client, user).json()  # no month -> current month
    assert body["month"] == f"{month}-01"
    assert body["status"] == "draft"
    assert Decimal(body["contribution"]) == Decimal("5000.00")
    assert Decimal(body["loan_repayment"]) == Decimal("1250.00")
    assert Decimal(body["other"]) == Decimal("500.00")
    assert Decimal(body["total"]) == Decimal("6750.00")


def test_only_my_own_month_is_returned(client, db_session):
    admin = make_admin_user(db_session, username="ded_iso", super_admin=True)
    mine = make_member(db_session, psn="PSN-DED-2", email="ded2@example.com")
    other = make_member(db_session, psn="PSN-DED-3", email="ded3@example.com")
    my_user = make_member_user(db_session, mine)
    other_user = make_member_user(db_session, other)

    _create(client, admin, mine, month="2026-11", contribution="5000.00")
    _create(client, admin, other, month="2026-11", contribution="9000.00")

    assert Decimal(_mine(client, my_user, "2026-11").json()["contribution"]) == Decimal("5000.00")
    assert Decimal(_mine(client, other_user, "2026-11").json()["contribution"]) == Decimal("9000.00")


def test_a_voided_month_reads_as_nothing(client, db_session):
    admin = make_admin_user(db_session, username="ded_void", super_admin=True)
    member = make_member(db_session, psn="PSN-DED-4", email="ded4@example.com")
    user = make_member_user(db_session, member)

    deduction_id = _create(client, admin, member, month="2026-11")
    res = client.post(
        f"/api/payroll-deductions/{deduction_id}/void",
        headers=auth_headers(admin),
        json={"reason": "deducted twice"},
    )
    assert res.status_code == 200, res.text

    body = _mine(client, user, "2026-11").json()
    assert body["status"] is None
    assert Decimal(body["total"]) == Decimal("0")


def test_officers_have_no_member_deduction_card(client, db_session):
    admin = make_admin_user(db_session, username="ded_officer", super_admin=True)
    assert _mine(client, admin).status_code == 403


def test_the_deductions_toggle_closes_the_card(client, db_session):
    admin = make_admin_user(db_session, username="ded_toggle", super_admin=True)
    member = make_member(db_session, psn="PSN-DED-5", email="ded5@example.com")
    user = make_member_user(db_session, member)
    _create(client, admin, member, month="2026-11")

    db_session.add(models.Settings(deductions_module_enabled=False))
    db_session.commit()

    res = _mine(client, user, "2026-11")
    assert res.status_code == 403, res.text
    assert "Deductions module is disabled" in res.json()["detail"]


def test_a_bad_month_is_rejected(client, db_session):
    member = make_member(db_session, psn="PSN-DED-6", email="ded6@example.com")
    user = make_member_user(db_session, member)

    res = _mine(client, user, "November")
    assert res.status_code == 422, res.text
