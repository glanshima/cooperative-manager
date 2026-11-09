"""The payroll entry worklist (2026-11).

An officer should not pick members out of a dropdown and guess amounts.
The worklist answers "who is still owed an entry for this month, and what
does the server expect?" so the queue shrinks as it is worked through.

  - a member appears only when something is due: a contribution, a loan
    instalment, or a financial member with no amount on file (which the
    officer must resolve rather than skip silently);
  - entering a member removes them from the queue; include_entered keeps
    them visible with their record's status;
  - amounts, arrears and warnings come from the expectation engine;
  - conflicted members stay visible and flagged (the read policy);
  - the endpoint needs deduction.view and the Deductions module.
"""
from datetime import date
from decimal import Decimal

from app import models
from tests.conftest import (
    auth_headers,
    grant_permission,
    make_admin_user,
    make_loan_type,
    make_member,
)

MONTH = "2026-11"


def _financial(db_session, psn, *, amount="5000.00"):
    return make_member(
        db_session,
        psn=psn,
        name=f"Member {psn}",
        monthly_contribution_amount=Decimal(amount) if amount else None,
        contribution_effective_from=date(2026, 1, 1) if amount else None,
    )


def _loan(db_session, member, loan_type, *, repaid="0.00"):
    loan = models.Loan(
        member_id=member.id,
        loan_type_id=loan_type.id,
        principal=Decimal("1200.00"),
        interest_amount=Decimal("0.00"),
        net_disbursed=Decimal("1200.00"),
        total_repayable=Decimal("1200.00"),
        monthly_installment=Decimal("100.00"),
        disbursement_date=date(2026, 1, 1),
        expected_end_date=date(2027, 1, 1),
        amount_repaid=Decimal(repaid),
        status=models.LoanStatus.ACTIVE,
    )
    db_session.add(loan)
    db_session.commit()
    db_session.refresh(loan)
    return loan


def _worklist(client, user, *, month=MONTH, include_entered=False):
    return client.get(
        "/api/payroll-deductions/worklist",
        headers=auth_headers(user),
        params={"month": month, "include_entered": str(include_entered).lower()},
    )


def _enter(client, admin, member, loan=None):
    lines = [{"category": "monthly_contribution", "amount": "5000.00"}]
    if loan is not None:
        lines.append({"category": "loan_repayment", "loan_id": str(loan.id), "amount": "100.00"})
    response = client.post(
        "/api/payroll-deductions",
        headers=auth_headers(admin),
        json={"member_id": str(member.id), "deduction_month": MONTH, "lines": lines},
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_the_queue_lists_members_who_owe_something_with_expected_amounts(client, db_session):
    admin = make_admin_user(db_session, username="worklist_admin", super_admin=True)
    member = _financial(db_session, "PSN-WL-1")
    loan_type = make_loan_type(db_session, "Worklist Loan")
    loan = _loan(db_session, member, loan_type, repaid="1000.00")

    response = _worklist(client, admin)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["month"] == "2026-11-01"
    assert body["due_count"] == 1
    assert body["entered_count"] == 0
    assert body["expected_total"] == "5100.00"
    item = body["items"][0]
    assert item["member_id"] == str(member.id)
    assert item["due_reasons"] == ["contribution", "loan_instalment"]
    assert item["expected_total"] == "5100.00"
    assert item["deduction_id"] is None
    amounts = {line["category"]: line["amount"] for line in item["lines"]}
    assert amounts == {"monthly_contribution": "5000.00", "loan_repayment": "100.00"}
    assert any(line["loan_id"] == str(loan.id) for line in item["lines"])


def test_entering_a_member_removes_them_from_the_queue(client, db_session):
    admin = make_admin_user(db_session, username="worklist_admin", super_admin=True)
    member = _financial(db_session, "PSN-WL-2")
    other = _financial(db_session, "PSN-WL-3")

    before = _worklist(client, admin).json()
    assert {item["member_id"] for item in before["items"]} == {str(member.id), str(other.id)}

    record = _enter(client, admin, member)

    after = _worklist(client, admin).json()
    assert [item["member_id"] for item in after["items"]] == [str(other.id)]
    assert after["due_count"] == 2
    assert after["entered_count"] == 1
    assert after["expected_total"] == "5000.00"

    included = _worklist(client, admin, include_entered=True).json()
    entered = next(item for item in included["items"] if item["member_id"] == str(member.id))
    assert entered["deduction_id"] == record["id"]
    assert entered["deduction_status"] == "draft"


def test_voiding_a_record_returns_the_member_to_the_queue(client, db_session):
    admin = make_admin_user(db_session, username="worklist_admin", super_admin=True)
    member = _financial(db_session, "PSN-WL-4")
    record = _enter(client, admin, member)
    assert _worklist(client, admin).json()["items"] == []

    response = client.post(
        "/api/payroll-deductions/bulk/void",
        headers=auth_headers(admin),
        json={"ids": [record["id"]], "reason": "Entered against the wrong month"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["results"][0]["ok"] is True

    assert [item["member_id"] for item in _worklist(client, admin).json()["items"]] == [
        str(member.id)
    ]


def test_a_financial_member_without_an_amount_is_listed_for_resolution(client, db_session):
    admin = make_admin_user(db_session, username="worklist_admin", super_admin=True)
    member = _financial(db_session, "PSN-WL-5", amount=None)

    item = _worklist(client, admin).json()["items"][0]

    assert item["member_id"] == str(member.id)
    assert item["due_reasons"] == ["contribution_amount_missing"]
    assert item["lines"] == []
    assert item["expected_total"] == "0.00"
    assert item["warnings"]


def test_members_with_nothing_due_are_left_out(client, db_session):
    admin = make_admin_user(db_session, username="worklist_admin", super_admin=True)
    make_member(
        db_session,
        psn="PSN-WL-6",
        status=models.MemberStatus.NON_FINANCIAL,
    )

    assert _worklist(client, admin).json()["items"] == []


def test_an_exited_member_with_a_loan_is_listed_with_the_exit_date(client, db_session):
    admin = make_admin_user(db_session, username="worklist_admin", super_admin=True)
    member = make_member(
        db_session,
        psn="PSN-WL-7",
        status=models.MemberStatus.NON_FINANCIAL,
        membership_exit_date=date(2026, 9, 15),
        membership_exit_reason="Left the service",
    )
    loan_type = make_loan_type(db_session, "Worklist Loan")
    _loan(db_session, member, loan_type, repaid="1000.00")

    item = _worklist(client, admin).json()["items"][0]

    assert item["member_status"] == "non_financial"
    assert item["membership_exit_date"] == "2026-09-15"
    assert item["due_reasons"] == ["loan_instalment"]
    assert item["expected_total"] == "100.00"


def test_arrears_are_shown_without_inflating_the_expected_total(client, db_session):
    admin = make_admin_user(db_session, username="worklist_admin", super_admin=True)
    member = _financial(db_session, "PSN-WL-8", amount=None)
    loan_type = make_loan_type(db_session, "Worklist Loan")
    _loan(db_session, member, loan_type, repaid="300.00")

    item = _worklist(client, admin).json()["items"][0]

    line = item["lines"][0]
    assert line["amount"] == "100.00"
    assert line["arrears"] == "700.00"
    assert line["months_behind"] == 7
    assert item["expected_total"] == "100.00"


def test_a_conflicted_member_stays_visible_and_flagged(client, db_session):
    officer = make_admin_user(db_session, username="worklist_conflicted", super_admin=True)
    linked = make_member(db_session, psn="PSN-WL-9")
    officer.member_id = linked.id
    db_session.commit()
    member = _financial(db_session, "PSN-WL-10")
    db_session.add(
        models.MemberRelationship(
            member_id=member.id,
            related_member_id=linked.id,
            conflict_of_interest=True,
            status=models.RelationshipStatus.ACTIVE,
        )
    )
    db_session.commit()

    body = _worklist(client, officer).json()

    flagged = next(item for item in body["items"] if item["member_id"] == str(member.id))
    assert flagged["conflicted"] is True
    assert all(
        item["conflicted"] is False for item in body["items"] if item["member_id"] != str(member.id)
    )


def test_the_worklist_needs_the_view_permission(client, db_session, seed_permissions):
    viewer = make_admin_user(db_session, username="worklist_viewer")
    grant_permission(db_session, viewer, "deduction.view")
    assert _worklist(client, viewer).status_code == 200

    outsider = make_admin_user(db_session, username="worklist_outsider")
    grant_permission(db_session, outsider, "deduction.create")
    assert _worklist(client, outsider).status_code == 403


def test_the_worklist_validates_the_month(client, db_session):
    admin = make_admin_user(db_session, username="worklist_admin", super_admin=True)

    assert _worklist(client, admin, month="2026-13").status_code == 422
    assert _worklist(client, admin, month="November").status_code == 422


def test_the_deductions_toggle_gates_the_worklist(client, db_session):
    admin = make_admin_user(db_session, username="worklist_admin", super_admin=True)
    settings = db_session.query(models.Settings).first()
    if settings is None:
        settings = models.Settings()
        db_session.add(settings)
    settings.deductions_module_enabled = False
    db_session.commit()

    response = _worklist(client, admin)

    assert response.status_code == 403
    assert "disabled" in response.json()["detail"]