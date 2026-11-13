"""
Payroll deductions module.

The contract these tests pin down:
  - drafting/submitting a monthly deduction never moves a loan balance;
  - confirming credits exactly the loan lines and completes a loan when
    the balance reaches zero;
  - voiding a confirmed record reverses those credits and reopens the
    loan;
  - a payroll non-deduction leaves the balance untouched and blocks a
    duplicate record for the same member/month until it is voided;
  - bulk actions isolate failures per record;
  - the module toggle and self-conflict guard apply here too.
"""
from datetime import date
from decimal import Decimal

from app import models
from tests.conftest import (
    auth_headers,
    make_admin_user,
    make_loan_type,
    make_member,
)


def _make_loan(db_session, member, loan_type, total_repayable=Decimal("1200.00"), amount_repaid=Decimal("0.00")):
    loan = models.Loan(
        member_id=member.id,
        loan_type_id=loan_type.id,
        principal=Decimal("1000.00"),
        interest_amount=Decimal("0.00"),
        net_disbursed=Decimal("1000.00"),
        total_repayable=total_repayable,
        monthly_installment=Decimal("100.00"),
        disbursement_date=date(2026, 1, 1),
        expected_end_date=date(2027, 1, 1),
        amount_repaid=amount_repaid,
        status=models.LoanStatus.ACTIVE,
    )
    db_session.add(loan)
    db_session.commit()
    db_session.refresh(loan)
    return loan


def _payload(member, loan, *, month="2026-11"):
    return {
        "member_id": str(member.id),
        "deduction_month": month,
        "payroll_reference": f"PAY-{month}",
        "lines": [
            {"category": "monthly_contribution", "amount": "2000.00"},
            {"category": "loan_repayment", "loan_id": str(loan.id), "amount": "500.00"},
            {"category": "other", "label": "Welfare", "amount": "100.00"},
        ],
    }


def _create(client, admin, member, loan, *, month="2026-11"):
    res = client.post(
        "/api/payroll-deductions", headers=auth_headers(admin), json=_payload(member, loan, month=month)
    )
    assert res.status_code == 201, res.text
    return res.json()


def _post(client, admin, path, **kwargs):
    return client.post(path, headers=auth_headers(admin), **kwargs)


def _loan(db_session, loan):
    db_session.expire_all()
    return db_session.query(models.Loan).filter(models.Loan.id == loan.id).one()


def test_draft_and_submission_do_not_touch_the_loan_balance(client, db_session):
    admin = make_admin_user(db_session, username="ded_admin", super_admin=True)
    member = make_member(db_session, psn="PSN-DED-1", email="ded1@example.com")
    loan_type = make_loan_type(db_session, "Capital Loan")
    loan = _make_loan(db_session, member, loan_type)

    body = _create(client, admin, member, loan)
    assert body["status"] == "draft"
    assert body["member_psn"] == "PSN-DED-1"
    assert Decimal(body["contribution_total"]) == Decimal("2000.00")
    assert Decimal(body["loan_total"]) == Decimal("500.00")
    assert Decimal(body["other_total"]) == Decimal("100.00")
    assert Decimal(body["grand_total"]) == Decimal("2600.00")
    assert _loan(db_session, loan).amount_repaid == Decimal("0.00")

    res = _post(client, admin, f"/api/payroll-deductions/{body['id']}/submit")
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "submitted"
    assert _loan(db_session, loan).amount_repaid == Decimal("0.00")


def test_confirm_credits_the_loan_and_void_reverses_it(client, db_session):
    admin = make_admin_user(db_session, username="ded_confirm", super_admin=True)
    member = make_member(db_session, psn="PSN-DED-2", email="ded2@example.com")
    loan_type = make_loan_type(db_session, "Short Term Loan")
    loan = _make_loan(db_session, member, loan_type)

    deduction = _create(client, admin, member, loan)
    _post(client, admin, f"/api/payroll-deductions/{deduction['id']}/submit")

    res = _post(client, admin, f"/api/payroll-deductions/{deduction['id']}/confirm")
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "confirmed"
    assert _loan(db_session, loan).amount_repaid == Decimal("500.00")

    # Confirmation is not repeatable.
    again = _post(client, admin, f"/api/payroll-deductions/{deduction['id']}/confirm")
    assert again.status_code == 400
    assert _loan(db_session, loan).amount_repaid == Decimal("500.00")

    res = _post(client, admin, f"/api/payroll-deductions/{deduction['id']}/void", json={"reason": "wrong month"})
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "void"
    assert res.json()["void_reason"] == "wrong month"
    reverted = _loan(db_session, loan)
    assert reverted.amount_repaid == Decimal("0.00")
    assert reverted.status == models.LoanStatus.ACTIVE


def test_multiple_active_loans_are_credited_independently(client, db_session):
    admin = make_admin_user(db_session, username="ded_multi", super_admin=True)
    member = make_member(db_session, psn="PSN-DED-MULTI", email="dedmulti@example.com")
    # A member cannot hold two active loans of the same type, so a
    # multi-loan deduction always spans different loan types.
    first_type = make_loan_type(db_session, "Capital Loan")
    second_type = make_loan_type(db_session, "Quick Loan")
    first = _make_loan(db_session, member, first_type, total_repayable=Decimal("1200.00"))
    # Paying this one off proves each loan is completed on its own,
    # not just the member's aggregate debt.
    second = _make_loan(db_session, member, second_type, total_repayable=Decimal("200.00"))

    payload = {
        "member_id": str(member.id),
        "deduction_month": "2026-11",
        "lines": [
            {"category": "loan_repayment", "loan_id": str(first.id), "amount": "300.00"},
            {"category": "loan_repayment", "loan_id": str(second.id), "amount": "200.00"},
        ],
    }
    res = client.post("/api/payroll-deductions", headers=auth_headers(admin), json=payload)
    assert res.status_code == 201, res.text
    body = res.json()
    assert Decimal(body["loan_total"]) == Decimal("500.00")
    assert len(body["lines"]) == 2

    _post(client, admin, f"/api/payroll-deductions/{body['id']}/submit")
    res = _post(client, admin, f"/api/payroll-deductions/{body['id']}/confirm")
    assert res.status_code == 200, res.text

    first_after = _loan(db_session, first)
    second_after = _loan(db_session, second)
    assert first_after.amount_repaid == Decimal("300.00")
    assert first_after.status == models.LoanStatus.ACTIVE
    assert second_after.amount_repaid == Decimal("200.00")
    assert second_after.status == models.LoanStatus.COMPLETED

    res = _post(
        client,
        admin,
        f"/api/payroll-deductions/{body['id']}/void",
        json={"reason": "payroll correction"},
    )
    assert res.status_code == 200, res.text
    first_reverted = _loan(db_session, first)
    second_reverted = _loan(db_session, second)
    assert first_reverted.amount_repaid == Decimal("0.00")
    assert first_reverted.status == models.LoanStatus.ACTIVE
    assert second_reverted.amount_repaid == Decimal("0.00")
    assert second_reverted.status == models.LoanStatus.ACTIVE


def test_confirm_completes_a_loan_and_void_reopens_it(client, db_session):
    admin = make_admin_user(db_session, username="ded_complete", super_admin=True)
    member = make_member(db_session, psn="PSN-DED-3", email="ded3@example.com")
    loan_type = make_loan_type(db_session, "Quick Loan")
    loan = _make_loan(
        db_session, member, loan_type, total_repayable=Decimal("500.00"), amount_repaid=Decimal("0.00")
    )

    deduction = _create(client, admin, member, loan)
    _post(client, admin, f"/api/payroll-deductions/{deduction['id']}/submit")
    res = _post(client, admin, f"/api/payroll-deductions/{deduction['id']}/confirm")
    assert res.status_code == 200, res.text

    completed = _loan(db_session, loan)
    assert completed.amount_repaid == Decimal("500.00")
    assert completed.status == models.LoanStatus.COMPLETED

    res = _post(client, admin, f"/api/payroll-deductions/{deduction['id']}/void", json={"reason": "payroll error"})
    assert res.status_code == 200, res.text

    reopened = _loan(db_session, loan)
    assert reopened.amount_repaid == Decimal("0.00")
    assert reopened.status == models.LoanStatus.ACTIVE


def test_void_cannot_reopen_a_loan_while_another_of_that_type_is_active(
    client, db_session
):
    admin = make_admin_user(db_session, username="ded_reopen_block", super_admin=True)
    member = make_member(db_session, psn="PSN-DED-6", email="ded6@example.com")
    loan_type = make_loan_type(db_session, "Quick Loan")
    loan = _make_loan(
        db_session, member, loan_type, total_repayable=Decimal("500.00"), amount_repaid=Decimal("0.00")
    )

    deduction = _create(client, admin, member, loan)
    _post(client, admin, f"/api/payroll-deductions/{deduction['id']}/submit")
    assert _post(client, admin, f"/api/payroll-deductions/{deduction['id']}/confirm").status_code == 200

    # A replacement loan of the same type went active after the original
    # was completed by this deduction, so reopening it would leave the
    # member holding two active loans of one type.
    replacement = _make_loan(
        db_session, member, loan_type, total_repayable=Decimal("300.00"), amount_repaid=Decimal("0.00")
    )

    res = _post(
        client,
        admin,
        f"/api/payroll-deductions/{deduction['id']}/void",
        json={"reason": "payroll error"},
    )
    assert res.status_code == 409
    assert "already has an active" in res.json()["detail"]

    db_session.expire_all()
    unchanged = _loan(db_session, loan)
    assert unchanged.amount_repaid == Decimal("500.00")
    assert unchanged.status == models.LoanStatus.COMPLETED
    assert _loan(db_session, replacement).status == models.LoanStatus.ACTIVE


def test_not_deducted_leaves_balance_alone_and_blocks_duplicate(client, db_session):
    admin = make_admin_user(db_session, username="ded_skip", super_admin=True)
    member = make_member(db_session, psn="PSN-DED-4", email="ded4@example.com")
    loan_type = make_loan_type(db_session, "Item Loan")
    loan = _make_loan(db_session, member, loan_type)

    deduction = _create(client, admin, member, loan)
    _post(client, admin, f"/api/payroll-deductions/{deduction['id']}/submit")

    res = _post(
        client,
        admin,
        f"/api/payroll-deductions/{deduction['id']}/not-deducted",
        json={"reason": "Member was on leave without pay"},
    )
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "not_deducted"
    assert res.json()["not_deducted_reason"] == "Member was on leave without pay"
    assert _loan(db_session, loan).amount_repaid == Decimal("0.00")

    duplicate = client.post(
        "/api/payroll-deductions", headers=auth_headers(admin), json=_payload(member, loan)
    )
    assert duplicate.status_code == 400
    assert "already exists" in duplicate.json()["detail"]

    # Voiding the not-deducted record clears the way for a correction.
    _post(client, admin, f"/api/payroll-deductions/{deduction['id']}/void", json={"reason": "re-enter"})
    replacement = client.post(
        "/api/payroll-deductions", headers=auth_headers(admin), json=_payload(member, loan)
    )
    assert replacement.status_code == 201, replacement.text

    # Voided records stay visible when explicitly filtered for, so the
    # ledger remains an append-only history.
    res = client.get(
        "/api/payroll-deductions",
        params={"month": "2026-11", "status": "void"},
        headers=auth_headers(admin),
    )
    assert res.status_code == 200, res.text
    voided = [record for record in res.json()["items"] if record["id"] == deduction["id"]]
    assert voided and voided[0]["void_reason"] == "re-enter"


def test_loan_line_validation(client, db_session):
    admin = make_admin_user(db_session, username="ded_validate", super_admin=True)
    member = make_member(db_session, psn="PSN-DED-5", email="ded5@example.com")
    other = make_member(db_session, psn="PSN-DED-6", email="ded6@example.com")
    loan_type = make_loan_type(db_session, "Capital Loan")
    other_loan = _make_loan(db_session, other, loan_type)

    # Someone else's loan.
    res = client.post(
        "/api/payroll-deductions", headers=auth_headers(admin), json=_payload(member, other_loan)
    )
    assert res.status_code == 400
    assert "does not belong" in res.json()["detail"]

    # A line larger than what remains on the loan.
    small_loan = _make_loan(
        db_session, member, loan_type, total_repayable=Decimal("300.00"), amount_repaid=Decimal("100.00")
    )
    payload = _payload(member, small_loan)
    payload["lines"] = [{"category": "loan_repayment", "loan_id": str(small_loan.id), "amount": "500.00"}]
    res = client.post("/api/payroll-deductions", headers=auth_headers(admin), json=payload)
    assert res.status_code == 400
    assert "remaining balance" in res.json()["detail"]

    # The same loan twice in one record is rejected by schema validation.
    payload = _payload(member, small_loan)
    payload["lines"] = [
        {"category": "loan_repayment", "loan_id": str(small_loan.id), "amount": "10.00"},
        {"category": "loan_repayment", "loan_id": str(small_loan.id), "amount": "20.00"},
    ]
    res = client.post("/api/payroll-deductions", headers=auth_headers(admin), json=payload)
    assert res.status_code == 422


def test_bulk_actions_report_per_record_results(client, db_session):
    admin = make_admin_user(db_session, username="ded_bulk", super_admin=True)
    loan_type = make_loan_type(db_session, "Capital Loan")
    member_a = make_member(db_session, psn="PSN-DED-7", email="ded7@example.com")
    member_b = make_member(db_session, psn="PSN-DED-8", email="ded8@example.com")
    loan_a = _make_loan(db_session, member_a, loan_type)
    loan_b = _make_loan(db_session, member_b, loan_type)

    deduction_a = _create(client, admin, member_a, loan_a)
    deduction_b = _create(client, admin, member_b, loan_b)

    res = _post(
        client,
        admin,
        "/api/payroll-deductions/bulk/submit",
        json={"ids": [deduction_a["id"], deduction_b["id"]]},
    )
    assert res.status_code == 200, res.text
    assert all(result["ok"] for result in res.json()["results"])

    # Confirm A individually so the bulk call sees one good and one stale record.
    _post(client, admin, f"/api/payroll-deductions/{deduction_a['id']}/confirm")

    res = _post(
        client,
        admin,
        "/api/payroll-deductions/bulk/confirm",
        json={"ids": [deduction_a["id"], deduction_b["id"]]},
    )
    assert res.status_code == 200, res.text
    by_id = {result["id"]: result for result in res.json()["results"]}
    assert by_id[deduction_a["id"]]["ok"] is False
    assert by_id[deduction_b["id"]]["ok"] is True
    assert _loan(db_session, loan_a).amount_repaid == Decimal("500.00")
    assert _loan(db_session, loan_b).amount_repaid == Decimal("500.00")

    missing_reason = _post(
        client,
        admin,
        "/api/payroll-deductions/bulk/not-deducted",
        json={"ids": [deduction_b["id"]]},
    )
    assert missing_reason.status_code == 422


def test_schedule_totals_exclude_not_deducted(client, db_session):
    admin = make_admin_user(db_session, username="ded_schedule", super_admin=True)
    loan_type = make_loan_type(db_session, "Capital Loan")
    member_a = make_member(db_session, psn="PSN-DED-9", email="ded9@example.com")
    member_b = make_member(db_session, psn="PSN-DED-10", email="ded10@example.com")
    loan_a = _make_loan(db_session, member_a, loan_type)
    loan_b = _make_loan(db_session, member_b, loan_type)

    skipped = _create(client, admin, member_a, loan_a)
    _post(client, admin, f"/api/payroll-deductions/{skipped['id']}/submit")
    _post(
        client,
        admin,
        f"/api/payroll-deductions/{skipped['id']}/not-deducted",
        json={"reason": "no pay"},
    )

    kept = _create(client, admin, member_b, loan_b)
    _post(client, admin, f"/api/payroll-deductions/{kept['id']}/submit")

    res = client.get(
        "/api/payroll-deductions/schedule",
        params={"month": "2026-11"},
        headers=auth_headers(admin),
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert len(body["records"]) == 2
    assert Decimal(body["totals"]["contribution_total"]) == Decimal("2000.00")
    assert Decimal(body["totals"]["loan_total"]) == Decimal("500.00")
    assert Decimal(body["totals"]["other_total"]) == Decimal("100.00")
    assert Decimal(body["totals"]["grand_total"]) == Decimal("2600.00")


def test_deductions_module_toggle_blocks_routes(client, db_session):
    settings = db_session.query(models.Settings).first()
    if settings is None:
        settings = models.Settings(deductions_module_enabled=False)
        db_session.add(settings)
    else:
        settings.deductions_module_enabled = False
    db_session.commit()

    admin = make_admin_user(db_session, username="ded_toggle", super_admin=True)

    res = client.get("/api/payroll-deductions", headers=auth_headers(admin))
    assert res.status_code == 403
    assert res.json()["detail"] == "The Deductions module is disabled by an administrator."

    # Settings stays reachable so the module can be re-enabled.
    assert client.get("/api/settings", headers=auth_headers(admin)).status_code == 200
    res = client.put(
        "/api/settings", headers=auth_headers(admin), json={"deductions_module_enabled": True}
    )
    assert res.status_code == 200
    assert client.get("/api/payroll-deductions", headers=auth_headers(admin)).status_code == 200


def test_requires_deduction_permissions(client, db_session, seed_permissions):
    admin = make_admin_user(db_session, username="ded_noperm")

    headers = auth_headers(admin)
    assert client.get("/api/payroll-deductions", headers=headers).status_code == 403
    res = client.post(
        f"/api/payroll-deductions/{'00000000-0000-0000-0000-000000000000'}/confirm",
        headers=headers,
    )
    assert res.status_code == 403
    assert "deduction.confirm" in res.json()["detail"]


def test_linked_admin_cannot_confirm_own_deduction(client, db_session):
    member = make_member(db_session, psn="PSN-DED-11", email="ded11@example.com")
    loan_type = make_loan_type(db_session, "Capital Loan")
    loan = _make_loan(db_session, member, loan_type)

    creator = make_admin_user(db_session, username="ded_creator", super_admin=True)
    deduction = _create(client, creator, member, loan)
    _post(client, creator, f"/api/payroll-deductions/{deduction['id']}/submit")

    linked = make_admin_user(db_session, username="ded_linked", super_admin=True, member_id=member.id)
    res = _post(client, linked, f"/api/payroll-deductions/{deduction['id']}/confirm")

    assert res.status_code == 409
    assert res.json()["detail"]["error"] == "self_conflict"
    assert _loan(db_session, loan).amount_repaid == Decimal("0.00")


def _catch_up_payload(member, loan, *, instalment="100.00", catch_up="600.00"):
    return {
        "member_id": str(member.id),
        "deduction_month": "2026-11",
        "lines": [
            {"category": "loan_repayment", "loan_id": str(loan.id), "amount": instalment},
            {"category": "loan_arrears", "loan_id": str(loan.id), "amount": catch_up},
        ],
    }


def test_an_arrears_line_credits_the_loan_it_catches_up(client, db_session):
    admin = make_admin_user(db_session, username="ded_arrears", super_admin=True)
    member = make_member(db_session, psn="PSN-DED-ARR", email="dedarr@example.com")
    loan_type = make_loan_type(db_session, "Long Loan")
    # Ten instalments fell due and three were collected, so 600 of past
    # months is missing on top of this month's 100.
    loan = _make_loan(db_session, member, loan_type, amount_repaid=Decimal("300.00"))

    res = client.post(
        "/api/payroll-deductions",
        headers=auth_headers(admin),
        json=_catch_up_payload(member, loan),
    )
    assert res.status_code == 201, res.text

    body = res.json()
    assert Decimal(body["loan_total"]) == Decimal("100.00")
    assert Decimal(body["arrears_total"]) == Decimal("600.00")
    assert Decimal(body["grand_total"]) == Decimal("700.00")
    lines = {line["category"]: line for line in body["lines"]}
    # Both figures come from the server, so a catch-up an officer shrank is
    # recorded as the decision it was.
    assert Decimal(lines["loan_arrears"]["expected_amount"]) == Decimal("600.00")

    _post(client, admin, f"/api/payroll-deductions/{body['id']}/submit")
    confirm = _post(client, admin, f"/api/payroll-deductions/{body['id']}/confirm")

    assert confirm.status_code == 200, confirm.text
    assert _loan(db_session, loan).amount_repaid == Decimal("1000.00")


def _loan_of(db_session, member):
    return db_session.query(models.Loan).filter(models.Loan.member_id == member.id).one()


def test_a_shrunken_catch_up_is_recorded_as_an_override(client, db_session):
    admin = make_admin_user(db_session, username="ded_arrears_part", super_admin=True)
    member = make_member(db_session, psn="PSN-DED-ARR2", email="dedarr2@example.com")
    loan_type = make_loan_type(db_session, "Long Loan")
    loan = _make_loan(db_session, member, loan_type, amount_repaid=Decimal("300.00"))

    res = client.post(
        "/api/payroll-deductions",
        headers=auth_headers(admin),
        json=_catch_up_payload(member, loan, catch_up="200.00"),
    )

    assert res.status_code == 201, res.text
    arrears = next(line for line in res.json()["lines"] if line["category"] == "loan_arrears")
    assert Decimal(arrears["amount"]) == Decimal("200.00")
    assert Decimal(arrears["expected_amount"]) == Decimal("600.00")


def test_loan_lines_together_cannot_exceed_the_remaining_balance(client, db_session):
    admin = make_admin_user(db_session, username="ded_arrears_cap", super_admin=True)
    member = make_member(db_session, psn="PSN-DED-ARR3", email="dedarr3@example.com")
    loan_type = make_loan_type(db_session, "Long Loan")
    # 50 left, but the schedule says 100 this month plus 600 of arrears.
    loan = _make_loan(db_session, member, loan_type, amount_repaid=Decimal("1150.00"))

    res = client.post(
        "/api/payroll-deductions",
        headers=auth_headers(admin),
        json=_catch_up_payload(member, loan, instalment="50.00", catch_up="50.00"),
    )

    assert res.status_code == 400, res.text
    assert "totalling 100.00" in res.json()["detail"]
    assert _loan(db_session, loan).amount_repaid == Decimal("1150.00")


def test_a_loan_takes_at_most_one_line_of_each_kind(client, db_session):
    admin = make_admin_user(db_session, username="ded_arrears_dup", super_admin=True)
    member = make_member(db_session, psn="PSN-DED-ARR4", email="dedarr4@example.com")
    loan_type = make_loan_type(db_session, "Long Loan")
    loan = _make_loan(db_session, member, loan_type)

    payload = _catch_up_payload(member, loan)
    payload["lines"].append(
        {"category": "loan_arrears", "loan_id": str(loan.id), "amount": "100.00"}
    )
    res = client.post("/api/payroll-deductions", headers=auth_headers(admin), json=payload)

    assert res.status_code == 422
    assert "one repayment line and one arrears line" in res.text


def test_an_arrears_line_has_to_name_a_loan(client, db_session):
    admin = make_admin_user(db_session, username="ded_arrears_shape", super_admin=True)
    member = make_member(db_session, psn="PSN-DED-ARR5", email="dedarr5@example.com")

    res = client.post(
        "/api/payroll-deductions",
        headers=auth_headers(admin),
        json={
            "member_id": str(member.id),
            "deduction_month": "2026-11",
            "lines": [{"category": "loan_arrears", "amount": "600.00"}],
        },
    )

    assert res.status_code == 422
    assert "requires loan_id" in res.text


def test_a_voided_catch_up_reopens_the_loan_it_closed(client, db_session):
    admin = make_admin_user(db_session, username="ded_arrears_void", super_admin=True)
    member = make_member(db_session, psn="PSN-DED-ARR6", email="dedarr6@example.com")
    loan_type = make_loan_type(db_session, "Long Loan")
    # 700 remaining: paying both lines settles the loan outright.
    loan = _make_loan(db_session, member, loan_type, amount_repaid=Decimal("500.00"))

    deduction = client.post(
        "/api/payroll-deductions",
        headers=auth_headers(admin),
        json=_catch_up_payload(member, loan, instalment="100.00", catch_up="600.00"),
    ).json()
    _post(client, admin, f"/api/payroll-deductions/{deduction['id']}/submit")
    _post(client, admin, f"/api/payroll-deductions/{deduction['id']}/confirm")
    assert _loan(db_session, loan).status == models.LoanStatus.COMPLETED

    res = _post(
        client,
        admin,
        f"/api/payroll-deductions/{deduction['id']}/void",
        json={"reason": "the months were miscounted"},
    )

    assert res.status_code == 200, res.text
    reverted = _loan(db_session, loan)
    assert reverted.amount_repaid == Decimal("500.00")
    assert reverted.status == models.LoanStatus.ACTIVE
