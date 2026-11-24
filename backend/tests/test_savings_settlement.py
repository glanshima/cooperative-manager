"""Savings ledger and exit settlement (2026-11).

Savings is a real subledger now, not a sum over payroll lines:

  - confirming a deduction credits the member's savings ledger; voiding it
    posts a counter-entry rather than editing history;
  - an exiting member's savings are applied to their loans oldest-first,
    the remainder becomes a payout the office owes them, and marking that
    payout paid records the handover.

Settlement is deliberately separate from recording the exit: the office
runs it after the member's final payroll month is confirmed, and after
that the member's payroll records are frozen.
"""
from datetime import date
from decimal import Decimal

from app import deduction_expectations, models, savings
from tests.conftest import (
    auth_headers,
    grant_permission,
    make_admin_user,
    make_loan_type,
    make_member,
)


def _make_loan(db_session, member, loan_type, *, disbursed_on, total, repaid=Decimal("0")):
    loan = models.Loan(
        member_id=member.id,
        loan_type_id=loan_type.id,
        principal=total,
        interest_amount=Decimal("0.00"),
        net_disbursed=total,
        total_repayable=total,
        monthly_installment=Decimal("100.00"),
        disbursement_date=disbursed_on,
        expected_end_date=date(disbursed_on.year + 1, disbursed_on.month, 1),
        amount_repaid=repaid,
        status=models.LoanStatus.ACTIVE,
    )
    db_session.add(loan)
    db_session.commit()
    db_session.refresh(loan)
    return loan


def _credit_savings(db_session, member, amount):
    db_session.add(
        models.SavingsEntry(
            member_id=member.id,
            entry_type=models.SavingsEntryType.CONTRIBUTION,
            amount=amount,
            note="Test contribution",
        )
    )
    db_session.commit()


def _exited_member(db_session, psn="STL-0001", email="stl1@example.com"):
    member = make_member(
        db_session,
        psn=psn,
        email=email,
        status=models.MemberStatus.NON_FINANCIAL,
        membership_exit_date=date(2026, 10, 31),
        membership_exit_reason="Resigned",
    )
    return member


def _settle(client, admin, member, body=None):
    return client.post(
        f"/api/members/{member.id}/settle-exit", json=body or {}, headers=auth_headers(admin)
    )


# ---------------------------------------------------------------------------
# Guards
# ---------------------------------------------------------------------------

def test_settling_requires_a_recorded_exit(client, db_session):
    admin = make_admin_user(db_session, username="stl_noexit", super_admin=True)
    member = make_member(db_session, psn="STL-0101", email="stl101@example.com")
    _credit_savings(db_session, member, Decimal("500.00"))

    res = _settle(client, admin, member)

    assert res.status_code == 409, res.text
    assert "Record the membership exit" in res.json()["detail"]
    assert savings.balance(db_session, member.id) == Decimal("500.00")


def test_nothing_to_settle_is_rejected(client, db_session):
    admin = make_admin_user(db_session, username="stl_empty", super_admin=True)
    member = _exited_member(db_session, psn="STL-0102", email="stl102@example.com")

    res = _settle(client, admin, member)

    assert res.status_code == 400, res.text
    assert "nothing to settle" in res.json()["detail"]
    assert db_session.query(models.MemberSettlement).count() == 0


def test_live_payroll_records_block_settlement(client, db_session):
    admin = make_admin_user(db_session, username="stl_live", super_admin=True)
    member = _exited_member(db_session, psn="STL-0103", email="stl103@example.com")
    _credit_savings(db_session, member, Decimal("500.00"))
    deduction = models.PayrollDeduction(
        member_id=member.id,
        deduction_month=date(2026, 10, 1),
        status=models.PayrollDeductionStatus.DRAFT,
    )
    db_session.add(deduction)
    db_session.commit()

    res = _settle(client, admin, member)

    assert res.status_code == 409, res.text
    assert "still in progress" in res.json()["detail"]


def test_a_settlement_cannot_be_repeated(client, db_session):
    admin = make_admin_user(db_session, username="stl_twice", super_admin=True)
    member = _exited_member(db_session, psn="STL-0104", email="stl104@example.com")
    _credit_savings(db_session, member, Decimal("500.00"))

    first = _settle(client, admin, member)
    assert first.status_code == 200, first.text

    second = _settle(client, admin, member)
    assert second.status_code == 409, second.text
    assert "already been settled" in second.json()["detail"]


# ---------------------------------------------------------------------------
# Applying savings to loans
# ---------------------------------------------------------------------------

def test_savings_offset_the_oldest_loan_first_and_close_it(client, db_session):
    admin = make_admin_user(db_session, username="stl_offset", super_admin=True)
    member = _exited_member(db_session, psn="STL-0201", email="stl201@example.com")
    older_type = make_loan_type(db_session, "Exit Loan")
    newer_type = make_loan_type(db_session, "Exit Loan (later)")
    older = _make_loan(
        db_session, member, older_type,
        disbursed_on=date(2025, 1, 15), total=Decimal("1000.00"), repaid=Decimal("200.00"),
    )
    newer = _make_loan(
        db_session, member, newer_type,
        disbursed_on=date(2025, 6, 15), total=Decimal("3000.00"),
    )
    _credit_savings(db_session, member, Decimal("1000.00"))

    # Older loan owes 800; the remaining 200 goes to the newer one.
    res = _settle(client, admin, member, {"note": "Final settlement"})
    assert res.status_code == 200, res.text
    body = res.json()

    assert Decimal(body["savings_balance"]) == Decimal("1000.00")
    assert Decimal(body["offset_total"]) == Decimal("1000.00")
    assert Decimal(body["payout_amount"]) == Decimal("0.00")
    assert body["payout_status"] == "paid"
    assert [item["loan_id"] for item in body["allocations"]] == [str(older.id), str(newer.id)]
    assert [Decimal(item["amount"]) for item in body["allocations"]] == [
        Decimal("800.00"),
        Decimal("200.00"),
    ]
    assert body["allocations"][0]["loan_type_name"] == "Exit Loan"

    db_session.expire_all()
    assert db_session.get(models.Loan, older.id).status == models.LoanStatus.COMPLETED
    assert db_session.get(models.Loan, newer.id).amount_repaid == Decimal("200.00")

    # The ledger was debited in full; no balance is left behind.
    assert savings.balance(db_session, member.id) == Decimal("0.00")


def test_settlement_posts_offset_and_payout_entries_to_the_ledger(client, db_session):
    admin = make_admin_user(db_session, username="stl_ledger", super_admin=True)
    member = _exited_member(db_session, psn="STL-0202", email="stl202@example.com")
    loan_type = make_loan_type(db_session, "Payout Loan")
    _make_loan(
        db_session, member, loan_type,
        disbursed_on=date(2025, 3, 1), total=Decimal("800.00"),
    )
    _credit_savings(db_session, member, Decimal("5000.00"))

    res = _settle(client, admin, member)
    assert res.status_code == 200, res.text
    body = res.json()

    assert Decimal(body["payout_amount"]) == Decimal("4200.00")
    assert body["payout_status"] == "pending"
    assert savings.balance(db_session, member.id) == Decimal("0.00")

    settlement = db_session.query(models.MemberSettlement).filter(
        models.MemberSettlement.member_id == member.id
    ).one()
    entries = (
        db_session.query(models.SavingsEntry)
        .filter(models.SavingsEntry.settlement_id == settlement.id)
        .all()
    )
    amounts = {entry.entry_type: entry.amount for entry in entries}
    assert amounts == {
        models.SavingsEntryType.EXIT_OFFSET: Decimal("800.00"),
        models.SavingsEntryType.EXIT_PAYOUT: Decimal("4200.00"),
    }


def test_preview_shows_the_balance_and_the_recorded_settlement(client, db_session):
    admin = make_admin_user(db_session, username="stl_preview", super_admin=True)
    member = _exited_member(db_session, psn="STL-0203", email="stl203@example.com")
    loan_type = make_loan_type(db_session, "Preview Loan")
    _make_loan(
        db_session, member, loan_type,
        disbursed_on=date(2025, 2, 1), total=Decimal("700.00"), repaid=Decimal("100.00"),
    )
    _credit_savings(db_session, member, Decimal("400.00"))

    before = client.get(f"/api/members/{member.id}/settlement", headers=auth_headers(admin))
    assert before.status_code == 200, before.text
    assert Decimal(before.json()["savings_balance"]) == Decimal("400.00")
    assert before.json()["active_loan_count"] == 1
    assert Decimal(before.json()["active_loan_outstanding"]) == Decimal("600.00")
    assert before.json()["settlement"] is None

    assert _settle(client, admin, member).status_code == 200

    after = client.get(f"/api/members/{member.id}/settlement", headers=auth_headers(admin))
    assert after.status_code == 200, after.text
    assert Decimal(after.json()["savings_balance"]) == Decimal("0.00")
    assert after.json()["settlement"]["payout_amount"] == "0.00"


# ---------------------------------------------------------------------------
# Payout: pending then paid
# ---------------------------------------------------------------------------

def test_mark_paid_records_the_handover_and_is_not_repeatable(client, db_session):
    admin = make_admin_user(db_session, username="stl_paid", super_admin=True)
    member = _exited_member(db_session, psn="STL-0301", email="stl301@example.com")
    _credit_savings(db_session, member, Decimal("1500.00"))
    settlement = _settle(client, admin, member, {"settled_on": "2026-11-01"})
    assert settlement.status_code == 200, settlement.text
    settlement_id = settlement.json()["id"]

    res = client.post(
        f"/api/members/{member.id}/settlements/mark-paid",
        json={"paid_on": "2026-11-15", "reference": "  CASH  0421 ", "paid_from": "cash"},
        headers=auth_headers(admin),
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["payout_status"] == "paid"
    assert body["paid_on"] == "2026-11-15"
    assert body["paid_reference"] == "CASH 0421"
    assert body["paid_from"] == "cash"

    again = client.post(
        f"/api/members/{member.id}/settlements/mark-paid",
        json={"reference": "CASH 0422", "paid_from": "cash"},
        headers=auth_headers(admin),
    )
    assert again.status_code == 409, again.text

    db_session.expire_all()
    stored = db_session.get(models.MemberSettlement, settlement_id)
    assert stored.payout_status == models.SettlementPayoutStatus.PAID
    assert stored.paid_reference == "CASH 0421"


def test_payout_cannot_be_dated_before_the_settlement(client, db_session):
    admin = make_admin_user(db_session, username="stl_backdate", super_admin=True)
    member = _exited_member(db_session, psn="STL-0302", email="stl302@example.com")
    _credit_savings(db_session, member, Decimal("300.00"))
    assert _settle(client, admin, member, {"settled_on": "2026-11-10"}).status_code == 200

    res = client.post(
        f"/api/members/{member.id}/settlements/mark-paid",
        json={"paid_on": "2026-11-01", "reference": "CASH 1", "paid_from": "bank"},
        headers=auth_headers(admin),
    )
    assert res.status_code == 400, res.text
    assert "before the settlement" in res.json()["detail"]


def test_a_blank_payout_reference_is_rejected(client, db_session):
    admin = make_admin_user(db_session, username="stl_blank", super_admin=True)
    member = _exited_member(db_session, psn="STL-0303", email="stl303@example.com")
    _credit_savings(db_session, member, Decimal("300.00"))
    assert _settle(client, admin, member).status_code == 200

    res = client.post(
        f"/api/members/{member.id}/settlements/mark-paid",
        json={"reference": "   "},
        headers=auth_headers(admin),
    )
    assert res.status_code == 422, res.text


# ---------------------------------------------------------------------------
# What settlement freezes
# ---------------------------------------------------------------------------

def test_settled_member_cannot_get_new_payroll_records(client, db_session):
    admin = make_admin_user(db_session, username="stl_frozen", super_admin=True)
    member = _exited_member(db_session, psn="STL-0401", email="stl401@example.com")
    _credit_savings(db_session, member, Decimal("500.00"))
    assert _settle(client, admin, member).status_code == 200

    res = client.post(
        "/api/payroll-deductions",
        json={
            "member_id": str(member.id),
            "deduction_month": "2026-11",
            "lines": [{"category": "other", "label": "Late charge", "amount": "10.00"}],
        },
        headers=auth_headers(admin),
    )
    assert res.status_code == 409, res.text
    assert "settled" in res.json()["detail"]


def test_a_settled_members_residual_loan_leaves_the_payroll_queue(client, db_session):
    """Settlement caps at the savings available, so a big loan can stay
    ACTIVE with a balance. The member's books are closed: payroll must not
    keep queueing that instalment."""
    admin = make_admin_user(db_session, username="stl_queue", super_admin=True)
    member = _exited_member(db_session, psn="STL-0402", email="stl402@example.com")
    loan_type = make_loan_type(db_session, "Residual Loan")
    loan = _make_loan(
        db_session, member, loan_type,
        disbursed_on=date(2025, 1, 1), total=Decimal("5000.00"),
    )
    _credit_savings(db_session, member, Decimal("1000.00"))
    assert _settle(client, admin, member).status_code == 200

    db_session.expire_all()
    assert db_session.get(models.Loan, loan.id).status == models.LoanStatus.ACTIVE

    expectation = deduction_expectations.for_member(db_session, member, date(2026, 11, 1))
    assert expectation.lines == []
    assert not expectation.is_due


# ---------------------------------------------------------------------------
# Permissions and audit
# ---------------------------------------------------------------------------

def test_settlement_requires_the_savings_permissions(client, db_session, seed_permissions):
    member = _exited_member(db_session, psn="STL-0501", email="stl501@example.com")
    _credit_savings(db_session, member, Decimal("500.00"))

    viewer = make_admin_user(db_session, username="stl_viewer")
    grant_permission(db_session, viewer, "savings.view")

    assert client.get(
        f"/api/members/{member.id}/settlement", headers=auth_headers(viewer)
    ).status_code == 200
    assert _settle(client, viewer, member).status_code == 403

    outsider = make_admin_user(db_session, username="stl_outsider")
    grant_permission(db_session, outsider, "member.view")
    assert client.get(
        f"/api/members/{member.id}/settlement", headers=auth_headers(outsider)
    ).status_code == 403


def test_settlement_and_payout_are_audited(client, db_session):
    admin = make_admin_user(db_session, username="stl_audit", super_admin=True)
    member = _exited_member(db_session, psn="STL-0502", email="stl502@example.com")
    _credit_savings(db_session, member, Decimal("800.00"))
    assert _settle(client, admin, member).status_code == 200
    assert client.post(
        f"/api/members/{member.id}/settlements/mark-paid",
        json={"reference": "BANK 77", "paid_from": "bank"},
        headers=auth_headers(admin),
    ).status_code == 200

    events = {
        event.event_type: event
        for event in db_session.query(models.AuditEvent)
        .filter(models.AuditEvent.event_type.in_(
            ["member.exit_settled", "member.exit_payout_paid"]
        ))
        .all()
    }
    assert set(events) == {"member.exit_settled", "member.exit_payout_paid"}
    assert events["member.exit_settled"].new_values["payout_amount"] == "800.00"
    assert events["member.exit_payout_paid"].new_values["paid_reference"] == "BANK 77"
