"""How interest is recovered from a loan (2026-11).

Three modes, resolved like the rate: the effective rate version wins, then
the loan type's cached terms, then the cooperative default. The loan type's
flat_charge is a processing fee paid SEPARATELY -- it must never appear in
the payout, the total repayable or the instalment.

  at_source            net = principal - interest, total = principal
  spread_over_tenure   net = principal,           total = principal + interest
  spread_first_months  net = principal,           total = principal + interest,
                       instalment = principal/tenure + interest/N for the
                       first N months, then principal/tenure
"""
from datetime import date
from decimal import Decimal

import pytest

from app import models
from app.loan_calc import (
    compute_loan_terms,
    expected_total_by_due_month,
    instalment_for_due_month,
)
from tests.conftest import auth_headers, make_admin_user, make_loan_type, make_member, make_settings

ZERO = Decimal("0.00")


def _terms(principal="100000.00", rate="0.10", tenure=10, mode=models.InterestDeductionMode.AT_SOURCE, months=None):
    return compute_loan_terms(Decimal(principal), Decimal(rate), tenure, mode, months)


def test_at_source_keeps_principal_as_total_and_withholds_interest():
    terms = _terms()
    assert terms.interest_amount == Decimal("10000.00")
    assert terms.net_disbursed == Decimal("90000.00")
    assert terms.total_repayable == Decimal("100000.00")
    assert terms.monthly_installment == Decimal("10000.00")
    assert terms.interest_installment == ZERO


def test_spread_over_tenure_pays_out_principal_and_adds_interest_to_total():
    terms = _terms(mode=models.InterestDeductionMode.SPREAD_OVER_TENURE)
    assert terms.net_disbursed == Decimal("100000.00")
    assert terms.total_repayable == Decimal("110000.00")
    assert terms.monthly_installment == Decimal("11000.00")
    assert terms.interest_installment == ZERO


def test_spread_first_months_adds_the_interest_share_on_top():
    terms = _terms(
        mode=models.InterestDeductionMode.SPREAD_FIRST_MONTHS, months=4
    )
    assert terms.net_disbursed == Decimal("100000.00")
    assert terms.total_repayable == Decimal("110000.00")
    assert terms.monthly_installment == Decimal("10000.00")
    assert terms.interest_installment == Decimal("2500.00")


def test_spread_first_months_rounds_interest_share_to_cents():
    # 10000 / 3 = 3333.333... -> 3333.33
    terms = _terms(
        principal="100000.00",
        rate="0.10",
        tenure=6,
        mode=models.InterestDeductionMode.SPREAD_FIRST_MONTHS,
        months=3,
    )
    assert terms.interest_installment == Decimal("3333.33")


def test_spread_first_months_requires_a_period_within_the_tenure():
    with pytest.raises(ValueError):
        _terms(mode=models.InterestDeductionMode.SPREAD_FIRST_MONTHS, months=None)
    with pytest.raises(ValueError):
        _terms(tenure=6, mode=models.InterestDeductionMode.SPREAD_FIRST_MONTHS, months=7)


def test_instalment_and_schedule_are_mode_aware():
    loan = models.Loan(
        principal=Decimal("100000.00"),
        interest_amount=Decimal("10000.00"),
        net_disbursed=Decimal("100000.00"),
        total_repayable=Decimal("110000.00"),
        monthly_installment=Decimal("10000.00"),
        interest_mode=models.InterestDeductionMode.SPREAD_FIRST_MONTHS,
        interest_spread_months=4,
        interest_installment=Decimal("2500.00"),
        disbursement_date=date(2026, 1, 1),
        expected_end_date=date(2027, 1, 1),
        amount_repaid=Decimal("0.00"),
        status=models.LoanStatus.ACTIVE,
    )

    assert instalment_for_due_month(loan, 1) == Decimal("12500.00")
    assert instalment_for_due_month(loan, 4) == Decimal("12500.00")
    assert instalment_for_due_month(loan, 5) == Decimal("10000.00")
    # After 4 instalments: 4*10000 + 4*2500 = 50000; scheduled never
    # exceeds the total repayable even after the last instalment.
    assert expected_total_by_due_month(loan, 4) == Decimal("50000.00")
    assert expected_total_by_due_month(loan, 10) == Decimal("110000.00")
    assert expected_total_by_due_month(loan, 20) == Decimal("110000.00")


def _disburse(client, admin, member, loan_type, *, principal="1000.00", disbursement_date="2026-11-01"):
    return client.post(
        "/api/loans",
        headers=auth_headers(admin),
        json={
            "member_id": str(member.id),
            "loan_type_id": str(loan_type.id),
            "principal": principal,
            "disbursement_date": disbursement_date,
        },
    )


def test_universal_fee_is_recorded_but_never_added_to_the_loan(client, db_session):
    make_settings(db_session, loan_form_fee=Decimal("25.00"))
    admin = make_admin_user(db_session, username="modes_admin", super_admin=True)
    member = make_member(db_session, psn="PSN-MODES-1", email="modes1@example.com")
    loan_type = make_loan_type(
        db_session, "Modes Fee Loan", interest_rate=Decimal("0.15"), tenure_months=10, flat_charge=Decimal("1.00")
    )

    response = _disburse(client, admin, member, loan_type, principal="1000.00")

    assert response.status_code == 201, response.text
    body = response.json()
    assert Decimal(body["total_repayable"]) == Decimal("1000.00")
    assert Decimal(body["net_disbursed"]) == Decimal("850.00")
    assert Decimal(body["interest_amount"]) == Decimal("150.00")
    assert Decimal(body["monthly_installment"]) == Decimal("100.00")
    # The cooperative's single fee snapshot is owed separately, outside every loan figure.
    assert Decimal(body["fee_amount"]) == Decimal("25.00")
    assert body["fee_status"] == "due"


def test_cooperative_default_is_used_when_the_type_inherits(client, db_session):
    db_session.add(
        models.Settings(
            loan_interest_mode=models.InterestDeductionMode.SPREAD_FIRST_MONTHS,
            loan_interest_spread_months=3,
        )
    )
    db_session.commit()
    admin = make_admin_user(db_session, username="modes_default", super_admin=True)
    member = make_member(db_session, psn="PSN-MODES-2", email="modes2@example.com")
    loan_type = make_loan_type(
        db_session, "Modes Inherit Loan", interest_rate=Decimal("0.10"), tenure_months=6
    )

    response = _disburse(client, admin, member, loan_type, principal="6000.00")

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["interest_mode"] == "spread_first_months"
    assert body["interest_spread_months"] == 3
    assert Decimal(body["net_disbursed"]) == Decimal("6000.00")
    assert Decimal(body["total_repayable"]) == Decimal("6600.00")
    assert Decimal(body["monthly_installment"]) == Decimal("1000.00")
    assert Decimal(body["interest_installment"]) == Decimal("200.00")


def test_rate_version_override_beats_the_loan_type(client, db_session):
    admin = make_admin_user(db_session, username="modes_version", super_admin=True)
    member = make_member(db_session, psn="PSN-MODES-3", email="modes3@example.com")
    loan_type = make_loan_type(
        db_session,
        "Modes Version Loan",
        interest_rate=Decimal("0.10"),
        tenure_months=6,
        interest_mode=models.InterestDeductionMode.AT_SOURCE,
    )
    db_session.add(
        models.LoanTypeRateVersion(
            loan_type_id=loan_type.id,
            interest_rate=Decimal("0.10"),
            tenure_months=6,
            flat_charge=Decimal("0"),
            interest_mode=models.InterestDeductionMode.SPREAD_OVER_TENURE,
            effective_from=date(2026, 1, 1),
        )
    )
    db_session.commit()

    response = _disburse(client, admin, member, loan_type, principal="6000.00")

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["interest_mode"] == "spread_over_tenure"
    assert Decimal(body["total_repayable"]) == Decimal("6600.00")
    assert Decimal(body["monthly_installment"]) == Decimal("1100.00")


def test_settings_reject_a_spread_period_without_the_matching_mode(client, db_session):
    admin = make_admin_user(db_session, username="modes_settings", super_admin=True)

    response = client.put(
        "/api/settings",
        headers=auth_headers(admin),
        json={"loan_interest_mode": "at_source", "loan_interest_spread_months": 3},
    )
    assert response.status_code == 400
    assert "only applies" in response.json()["detail"]

    response = client.put(
        "/api/settings",
        headers=auth_headers(admin),
        json={"loan_interest_mode": "spread_first_months"},
    )
    assert response.status_code == 400
    assert "spread period is required" in response.json()["detail"]


def test_rate_version_rejects_a_period_longer_than_the_tenure(client, db_session):
    admin = make_admin_user(db_session, username="modes_rate", super_admin=True)
    loan_type = make_loan_type(db_session, "Modes Rate Loan", tenure_months=6)

    response = client.post(
        f"/api/loan-types/{loan_type.id}/rate-versions",
        headers=auth_headers(admin),
        json={
            "interest_rate": 0.1,
            "tenure_months": 6,
            "interest_mode": "spread_first_months",
            "interest_spread_months": 7,
            "effective_from": "2026-11-01",
        },
    )
    assert response.status_code == 422
    assert "between 1 and the tenure" in response.text
