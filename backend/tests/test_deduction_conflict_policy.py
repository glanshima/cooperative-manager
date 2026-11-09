"""Conflict of interest at the payroll desk (2026-11).

Recording a deduction is not the same kind of act as deciding one. The
amounts are already agreed -- the contribution on the member record, the
instalment fixed at disbursement -- so typing them in is clerical and a
conflicted officer may do it. What stays reserved to an unconflicted
officer is any DISCRETION over a related member's money:

  - entering an amount that differs from the expectation (or an 'other'
    line, which has no expectation at all);
  - submitting a draft that contains such an override;
  - confirming, marking not deducted, or voiding -- the steps that
    recognise, excuse or reverse money.

A denied attempt must leave nothing behind: the denial itself is audited,
and writing an audit event commits the session.
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

MONTH = "2026-11"


def _member(db_session, psn="PSN-DCP-1"):
    return make_member(
        db_session,
        psn=psn,
        name="Conflict Policy Member",
        monthly_contribution_amount=Decimal("5000.00"),
        contribution_effective_from=date(2026, 1, 1),
    )


def _loan(db_session, member, loan_type):
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
        amount_repaid=Decimal("1000.00"),
        status=models.LoanStatus.ACTIVE,
    )
    db_session.add(loan)
    db_session.commit()
    db_session.refresh(loan)
    return loan


def _conflicted_officer(db_session, member, *, username="dcp_conflicted"):
    """An officer whose own member record is flagged as a conflict of
    interest against `member`."""
    own = make_member(db_session, psn=f"{member.psn}-KIN", name="Officer Kin")
    officer = make_admin_user(db_session, username=username, super_admin=True, member_id=own.id)
    db_session.add(
        models.MemberRelationship(
            member_id=member.id,
            related_member_id=own.id,
            conflict_of_interest=True,
            status=models.RelationshipStatus.ACTIVE,
        )
    )
    db_session.commit()
    return officer


def _payload(member, loan, *, contribution="5000.00", loan_amount="100.00", extra=False):
    lines = [
        {"category": "monthly_contribution", "amount": contribution},
        {"category": "loan_repayment", "loan_id": str(loan.id), "amount": loan_amount},
    ]
    if extra:
        lines.append({"category": "other", "label": "Welfare", "amount": "100.00"})
    return {"member_id": str(member.id), "deduction_month": MONTH, "lines": lines}


def _records(db_session, member):
    db_session.expire_all()
    return (
        db_session.query(models.PayrollDeduction)
        .filter(
            models.PayrollDeduction.member_id == member.id,
            models.PayrollDeduction.deduction_month == date(2026, 11, 1),
        )
        .all()
    )


def _fixture(db_session):
    member = _member(db_session)
    loan_type = make_loan_type(db_session, "Conflict Policy Loan")
    loan = _loan(db_session, member, loan_type)
    return member, loan


def test_a_conflicted_officer_may_record_the_expected_amounts(client, db_session):
    member, loan = _fixture(db_session)
    officer = _conflicted_officer(db_session, member)

    response = client.post(
        "/api/payroll-deductions", headers=auth_headers(officer), json=_payload(member, loan)
    )

    assert response.status_code == 201, response.text
    lines = {line["category"]: line for line in response.json()["lines"]}
    assert lines["monthly_contribution"]["expected_amount"] == "5000.00"
    assert lines["loan_repayment"]["expected_amount"] == "100.00"


def test_a_conflicted_officer_cannot_type_a_different_amount(client, db_session):
    member, loan = _fixture(db_session)
    officer = _conflicted_officer(db_session, member)

    response = client.post(
        "/api/payroll-deductions",
        headers=auth_headers(officer),
        json=_payload(member, loan, contribution="2000.00"),
    )

    assert response.status_code == 409, response.text
    assert response.json()["detail"]["error"] == "member_conflict"
    # The denial is audited, and that commit must not smuggle the draft in.
    assert _records(db_session, member) == []


def test_an_other_deduction_is_discretion_even_at_a_round_number(client, db_session):
    member, loan = _fixture(db_session)
    officer = _conflicted_officer(db_session, member)

    response = client.post(
        "/api/payroll-deductions",
        headers=auth_headers(officer),
        json=_payload(member, loan, extra=True),
    )

    assert response.status_code == 409, response.text
    assert response.json()["detail"]["error"] == "member_conflict"
    assert _records(db_session, member) == []


def test_an_unconflicted_officer_may_override(client, db_session):
    member, loan = _fixture(db_session)
    officer = make_admin_user(db_session, username="dcp_unconflicted", super_admin=True)

    response = client.post(
        "/api/payroll-deductions",
        headers=auth_headers(officer),
        json=_payload(member, loan, contribution="2000.00", extra=True),
    )

    assert response.status_code == 201, response.text
    lines = {line["category"]: line for line in response.json()["lines"]}
    assert lines["monthly_contribution"]["amount"] == "2000.00"
    assert lines["monthly_contribution"]["expected_amount"] == "5000.00"


def test_a_conflicted_officer_may_edit_a_draft_at_the_expected_amounts(client, db_session):
    member, loan = _fixture(db_session)
    officer = _conflicted_officer(db_session, member)
    created = client.post(
        "/api/payroll-deductions", headers=auth_headers(officer), json=_payload(member, loan)
    ).json()

    response = client.put(
        f"/api/payroll-deductions/{created['id']}",
        headers=auth_headers(officer),
        json={"note": "Checked against the payroll sheet", "lines": _payload(member, loan)["lines"]},
    )

    assert response.status_code == 200, response.text
    assert response.json()["note"] == "Checked against the payroll sheet"


def test_a_denied_edit_leaves_the_stored_draft_untouched(client, db_session):
    member, loan = _fixture(db_session)
    officer = _conflicted_officer(db_session, member)
    created = client.post(
        "/api/payroll-deductions", headers=auth_headers(officer), json=_payload(member, loan)
    ).json()

    response = client.put(
        f"/api/payroll-deductions/{created['id']}",
        headers=auth_headers(officer),
        json={"note": "Smuggled in", "lines": _payload(member, loan, contribution="1000.00")["lines"]},
    )

    assert response.status_code == 409, response.text
    stored = _records(db_session, member)[0]
    assert stored.note is None
    assert all(line.amount == line.expected_amount for line in stored.lines)


def test_a_conflicted_officer_may_submit_agreed_amounts_but_not_overrides(client, db_session):
    member, loan = _fixture(db_session)
    officer = _conflicted_officer(db_session, member)
    clean = client.post(
        "/api/payroll-deductions", headers=auth_headers(officer), json=_payload(member, loan)
    ).json()

    submitted = client.post(
        f"/api/payroll-deductions/{clean['id']}/submit", headers=auth_headers(officer)
    )
    assert submitted.status_code == 200, submitted.text
    assert submitted.json()["status"] == "submitted"

    # A second month's draft, overridden by an unconflicted colleague.
    other = make_admin_user(db_session, username="dcp_colleague", super_admin=True)
    payload = _payload(member, loan, contribution="2000.00")
    payload["deduction_month"] = "2026-12"
    overridden = client.post(
        "/api/payroll-deductions", headers=auth_headers(other), json=payload
    ).json()

    refused = client.post(
        f"/api/payroll-deductions/{overridden['id']}/submit", headers=auth_headers(officer)
    )
    assert refused.status_code == 409, refused.text
    assert refused.json()["detail"]["error"] == "member_conflict"


def test_bulk_submit_reports_the_override_refusal_per_record(client, db_session):
    member, loan = _fixture(db_session)
    officer = _conflicted_officer(db_session, member)
    other = make_admin_user(db_session, username="dcp_colleague", super_admin=True)
    payload = _payload(member, loan, contribution="2000.00")
    record = client.post(
        "/api/payroll-deductions", headers=auth_headers(other), json=payload
    ).json()

    response = client.post(
        "/api/payroll-deductions/bulk/submit",
        headers=auth_headers(officer),
        json={"ids": [record["id"]]},
    )

    assert response.status_code == 200, response.text
    result = response.json()["results"][0]
    assert result["ok"] is False
    assert "conflict" in result["detail"].lower()


def test_money_recognition_stays_with_an_unconflicted_officer(client, db_session):
    member, loan = _fixture(db_session)
    officer = _conflicted_officer(db_session, member)
    record = client.post(
        "/api/payroll-deductions", headers=auth_headers(officer), json=_payload(member, loan)
    ).json()
    client.post(f"/api/payroll-deductions/{record['id']}/submit", headers=auth_headers(officer))

    confirm = client.post(
        f"/api/payroll-deductions/{record['id']}/confirm", headers=auth_headers(officer)
    )
    assert confirm.status_code == 409, confirm.text
    assert confirm.json()["detail"]["error"] == "member_conflict"

    not_deducted = client.post(
        f"/api/payroll-deductions/{record['id']}/not-deducted",
        headers=auth_headers(officer),
        json={"reason": "Payroll skipped this member"},
    )
    assert not_deducted.status_code == 409, not_deducted.text

    void = client.post(
        f"/api/payroll-deductions/{record['id']}/void",
        headers=auth_headers(officer),
        json={"reason": "Entered in error"},
    )
    assert void.status_code == 409, void.text

    db_session.expire_all()
    assert db_session.query(models.Loan).filter(models.Loan.id == loan.id).one().amount_repaid == Decimal("1000.00")


def test_an_officer_may_record_their_own_expected_deduction_but_not_confirm_it(client, db_session):
    member, loan = _fixture(db_session)
    officer = make_admin_user(
        db_session, username="dcp_self", super_admin=True, member_id=member.id
    )

    created = client.post(
        "/api/payroll-deductions", headers=auth_headers(officer), json=_payload(member, loan)
    )
    assert created.status_code == 201, created.text

    client.post(
        f"/api/payroll-deductions/{created.json()['id']}/submit", headers=auth_headers(officer)
    )
    confirm = client.post(
        f"/api/payroll-deductions/{created.json()['id']}/confirm", headers=auth_headers(officer)
    )
    assert confirm.status_code == 409, confirm.text
    assert confirm.json()["detail"]["error"] == "self_conflict"