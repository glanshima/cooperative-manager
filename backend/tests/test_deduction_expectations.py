"""What payroll should pre-fill for a member's month (2026-11).

The instalment is fixed at disbursement and the contribution is agreed on
the member record, so the officer should not retype either. These tests
pin down the arithmetic and, just as importantly, the cases where the
server must NOT invent a figure:

  - the first instalment falls due the month AFTER disbursement;
  - a loan line is capped at the remaining balance and net of verified
    repayments recorded for that same month (never of unverified claims,
    never of another month's payment);
  - arrears are reported, not added to the pre-filled line;
  - repayments with no recorded month are surfaced, not guessed at;
  - expected_amount is always derived server-side, so a typed override
    stays visibly different from the expectation.
"""
from datetime import date
from decimal import Decimal

from app import deduction_expectations as expectations
from app import models
from tests.conftest import (
    auth_headers,
    make_admin_user,
    make_loan_type,
    make_member,
)

MONTH = date(2026, 11, 1)


def _loan(
    db_session,
    member,
    loan_type,
    *,
    disbursed=date(2026, 1, 1),
    total=Decimal("1200.00"),
    repaid=Decimal("0.00"),
    instalment=Decimal("100.00"),
    status=models.LoanStatus.ACTIVE,
):
    loan = models.Loan(
        member_id=member.id,
        loan_type_id=loan_type.id,
        principal=total,
        interest_amount=Decimal("0.00"),
        net_disbursed=total,
        total_repayable=total,
        monthly_installment=instalment,
        disbursement_date=disbursed,
        expected_end_date=date(2027, 1, 1),
        amount_repaid=repaid,
        status=status,
    )
    db_session.add(loan)
    db_session.commit()
    db_session.refresh(loan)
    return loan


def _repayment(db_session, loan, *, month, amount="100.00", status=models.RepaymentVerificationStatus.VERIFIED):
    repayment = models.LoanRepayment(
        loan_id=loan.id,
        member_id=loan.member_id,
        payment_month=month,
        amount_claimed=Decimal(amount),
        payment_reference="TRF-EXPECT",
        receipt_image_base64="aGVsbG8=",
        receipt_content_type="image/png",
        status=status,
    )
    db_session.add(repayment)
    db_session.commit()
    return repayment


def _member(db_session, *, amount=Decimal("5000.00"), status=models.MemberStatus.FINANCIAL):
    return make_member(
        db_session,
        psn="PSN-EXPECT",
        name="Expectation Member",
        status=status,
        monthly_contribution_amount=amount,
        contribution_effective_from=date(2026, 1, 1) if amount is not None else None,
    )


def _loan_lines(expectation):
    return [
        line
        for line in expectation.lines
        if line.category == models.PayrollDeductionLineCategory.LOAN_REPAYMENT
    ]


def test_contribution_comes_from_the_member_record(db_session):
    member = _member(db_session)

    expectation = expectations.for_member(db_session, member, MONTH)

    assert expectation.contribution_amount == Decimal("5000.00")
    assert expectation.due_reasons == [expectations.DUE_CONTRIBUTION]
    assert expectation.total == Decimal("5000.00")


def test_financial_member_without_an_amount_is_flagged_not_guessed(db_session):
    member = _member(db_session, amount=None)

    expectation = expectations.for_member(db_session, member, MONTH)

    assert expectation.contribution_amount is None
    assert expectation.lines == []
    assert expectations.DUE_CONTRIBUTION_AMOUNT_MISSING in expectation.due_reasons
    assert expectation.warnings


def test_non_financial_member_owes_no_contribution_but_still_repays_loans(db_session):
    member = _member(db_session, status=models.MemberStatus.NON_FINANCIAL)
    loan_type = make_loan_type(db_session, "Expect Loan")
    _loan(db_session, member, loan_type, repaid=Decimal("1000.00"))

    expectation = expectations.for_member(db_session, member, MONTH)

    assert expectation.contribution_amount is None
    assert expectation.due_reasons == [expectations.DUE_LOAN_INSTALMENT]
    assert len(_loan_lines(expectation)) == 1


def test_first_instalment_is_due_the_month_after_disbursement(db_session):
    member = _member(db_session, amount=None)
    loan_type = make_loan_type(db_session, "Expect Loan")
    _loan(db_session, member, loan_type, disbursed=MONTH)

    disbursement_month = expectations.for_member(db_session, member, MONTH)
    following_month = expectations.for_member(db_session, member, date(2026, 12, 1))

    assert _loan_lines(disbursement_month) == []
    assert expectations.DUE_LOAN_INSTALMENT not in disbursement_month.due_reasons
    assert _loan_lines(following_month)[0].amount == Decimal("100.00")


def test_instalment_is_capped_at_the_remaining_balance(db_session):
    member = _member(db_session, amount=None)
    loan_type = make_loan_type(db_session, "Expect Loan")
    _loan(db_session, member, loan_type, repaid=Decimal("1150.00"))

    expectation = expectations.for_member(db_session, member, MONTH)

    assert _loan_lines(expectation)[0].amount == Decimal("50.00")


def test_verified_payment_for_the_month_is_netted_off(db_session):
    member = _member(db_session, amount=None)
    loan_type = make_loan_type(db_session, "Expect Loan")
    loan = _loan(db_session, member, loan_type, repaid=Decimal("1000.00"))
    _repayment(db_session, loan, month=MONTH)

    expectation = expectations.for_member(db_session, member, MONTH)

    line = _loan_lines(expectation)[0]
    assert line.amount == Decimal("0.00")
    # Nothing left to enter for this loan, but it stays visible so the
    # officer can see it was already covered.
    assert expectations.DUE_LOAN_INSTALMENT not in expectation.due_reasons


def test_unverified_claims_and_other_months_do_not_reduce_the_instalment(db_session):
    member = _member(db_session, amount=None)
    loan_type = make_loan_type(db_session, "Expect Loan")
    loan = _loan(db_session, member, loan_type, repaid=Decimal("900.00"))
    _repayment(
        db_session,
        loan,
        month=MONTH,
        status=models.RepaymentVerificationStatus.AWAITING_VERIFICATION,
    )
    _repayment(db_session, loan, month=date(2026, 10, 1))

    expectation = expectations.for_member(db_session, member, MONTH)

    assert _loan_lines(expectation)[0].amount == Decimal("100.00")


def test_arrears_are_reported_without_inflating_the_line(db_session):
    member = _member(db_session, amount=None)
    loan_type = make_loan_type(db_session, "Expect Loan")
    # Ten instalments fell due (Feb..Nov) but only three were collected.
    _loan(db_session, member, loan_type, repaid=Decimal("300.00"))

    expectation = expectations.for_member(db_session, member, MONTH)

    line = _loan_lines(expectation)[0]
    assert line.amount == Decimal("100.00")
    assert line.arrears == Decimal("700.00")
    assert line.months_behind == 7


def test_payment_without_a_recorded_month_is_surfaced_as_a_warning(db_session):
    member = _member(db_session, amount=None)
    loan_type = make_loan_type(db_session, "Expect Loan")
    loan = _loan(db_session, member, loan_type, repaid=Decimal("1000.00"))
    _repayment(db_session, loan, month=None)

    expectation = expectations.for_member(db_session, member, MONTH)

    assert _loan_lines(expectation)[0].amount == Decimal("100.00")
    assert any("no recorded payment month" in warning for warning in expectation.warnings)


def test_completed_loans_expect_nothing(db_session):
    member = _member(db_session, amount=None)
    loan_type = make_loan_type(db_session, "Expect Loan")
    _loan(
        db_session,
        member,
        loan_type,
        repaid=Decimal("1200.00"),
        status=models.LoanStatus.COMPLETED,
    )

    expectation = expectations.for_member(db_session, member, MONTH)

    assert _loan_lines(expectation) == []
    assert expectations.DUE_LOAN_INSTALMENT not in expectation.due_reasons


def test_months_between_counts_inclusively_and_never_goes_negative():
    assert expectations.months_between(date(2026, 2, 1), date(2026, 11, 1)) == 10
    assert expectations.months_between(date(2026, 11, 1), date(2026, 11, 1)) == 1
    assert expectations.months_between(date(2026, 12, 1), date(2027, 1, 1)) == 2
    assert expectations.months_between(date(2026, 11, 1), date(2026, 10, 1)) == 0


def _draft_payload(member, loan, *, month="2026-11", contribution="5000.00", loan_amount="100.00"):
    return {
        "member_id": str(member.id),
        "deduction_month": month,
        "lines": [
            {"category": "monthly_contribution", "amount": contribution},
            {"category": "loan_repayment", "loan_id": str(loan.id), "amount": loan_amount},
            {"category": "other", "label": "Welfare", "amount": "100.00"},
        ],
    }


def test_creating_a_draft_stamps_the_server_expectation(client, db_session):
    admin = make_admin_user(db_session, username="expect_admin", super_admin=True)
    member = _member(db_session)
    loan_type = make_loan_type(db_session, "Expect Loan")
    loan = _loan(db_session, member, loan_type, repaid=Decimal("1000.00"))

    response = client.post(
        "/api/payroll-deductions",
        headers=auth_headers(admin),
        json=_draft_payload(member, loan),
    )

    assert response.status_code == 201, response.text
    lines = {line["category"]: line for line in response.json()["lines"]}
    assert lines["monthly_contribution"]["expected_amount"] == "5000.00"
    assert lines["loan_repayment"]["expected_amount"] == "100.00"
    assert lines["other"]["expected_amount"] is None


def test_an_override_keeps_the_expectation_visible(client, db_session):
    admin = make_admin_user(db_session, username="expect_admin", super_admin=True)
    member = _member(db_session)
    loan_type = make_loan_type(db_session, "Expect Loan")
    loan = _loan(db_session, member, loan_type, repaid=Decimal("600.00"))

    response = client.post(
        "/api/payroll-deductions",
        headers=auth_headers(admin),
        json=_draft_payload(member, loan, contribution="2000.00", loan_amount="500.00"),
    )

    assert response.status_code == 201, response.text
    lines = {line["category"]: line for line in response.json()["lines"]}
    assert lines["monthly_contribution"]["amount"] == "2000.00"
    assert lines["monthly_contribution"]["expected_amount"] == "5000.00"
    assert lines["loan_repayment"]["amount"] == "500.00"
    assert lines["loan_repayment"]["expected_amount"] == "100.00"


def test_a_client_supplied_expectation_is_ignored(client, db_session):
    admin = make_admin_user(db_session, username="expect_admin", super_admin=True)
    member = _member(db_session)
    loan_type = make_loan_type(db_session, "Expect Loan")
    loan = _loan(db_session, member, loan_type, repaid=Decimal("1000.00"))
    payload = _draft_payload(member, loan)
    payload["lines"][0]["expected_amount"] = "1.00"

    response = client.post(
        "/api/payroll-deductions", headers=auth_headers(admin), json=payload
    )

    assert response.status_code == 201, response.text
    lines = {line["category"]: line for line in response.json()["lines"]}
    assert lines["monthly_contribution"]["expected_amount"] == "5000.00"


def test_moving_a_draft_to_another_month_reprices_its_lines(client, db_session):
    admin = make_admin_user(db_session, username="expect_admin", super_admin=True)
    member = _member(db_session)
    loan_type = make_loan_type(db_session, "Expect Loan")
    # Disbursed in November: no instalment is due that month, one is in
    # December, and the balance is nearly cleared by then.
    loan = _loan(db_session, member, loan_type, disbursed=MONTH, repaid=Decimal("1150.00"))
    created = client.post(
        "/api/payroll-deductions",
        headers=auth_headers(admin),
        json=_draft_payload(member, loan, loan_amount="50.00"),
    )
    assert created.status_code == 201, created.text

    response = client.put(
        f"/api/payroll-deductions/{created.json()['id']}",
        headers=auth_headers(admin),
        json={"deduction_month": "2026-12"},
    )

    assert response.status_code == 200, response.text
    lines = {line["category"]: line for line in response.json()["lines"]}
    assert lines["loan_repayment"]["expected_amount"] == "50.00"