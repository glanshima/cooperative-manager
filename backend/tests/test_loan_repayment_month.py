"""The payroll month a bank-transfer repayment covers (2026-11).

A member can pay an instalment directly instead of through payroll. For
the ledger to net that payment off the month's expectation, the record
must carry the month it was FOR -- the submission timestamp is not a
payment date, and guessing one would double-charge the member.

  - payment_month is required, is a 'YYYY-MM' label, and is stored as the
    first of that month.
  - It cannot be a future month, nor a month before the loan existed.
  - Records made before this field existed keep a NULL month; nothing
    backfills them.
"""
from datetime import date
from decimal import Decimal

from app import models
from tests.conftest import (
    auth_headers,
    make_loan_type,
    make_member,
    make_member_user,
)


def _loan(db_session, member, loan_type, disbursement_date):
    loan = models.Loan(
        member_id=member.id,
        loan_type_id=loan_type.id,
        principal=Decimal("120000.00"),
        interest_amount=Decimal("0.00"),
        net_disbursed=Decimal("120000.00"),
        total_repayable=Decimal("120000.00"),
        monthly_installment=Decimal("10000.00"),
        disbursement_date=disbursement_date,
        expected_end_date=date(disbursement_date.year + 1, disbursement_date.month, 1),
        amount_repaid=Decimal("0.00"),
        status=models.LoanStatus.ACTIVE,
    )
    db_session.add(loan)
    db_session.commit()
    db_session.refresh(loan)
    return loan


def _submit(client, user, loan, **overrides):
    payload = {
        "amount_claimed": "10000.00",
        "payment_month": date.today().strftime("%Y-%m"),
        "payment_reference": "TRF-REP-MONTH",
        "receipt_image_base64": "aGVsbG8=",
        "receipt_content_type": "image/png",
    }
    payload.update(overrides)
    return client.post(
        f"/api/loans/{loan.id}/repayments", headers=auth_headers(user), json=payload
    )


def _fixture(db_session, *, disbursement_date=None):
    member = make_member(db_session, psn="PSN-REPMON", name="Rep Month")
    user = make_member_user(db_session, member)
    loan_type = make_loan_type(db_session, "Rep Month Loan")
    loan = _loan(db_session, member, loan_type, disbursement_date or date.today().replace(day=1))
    return member, user, loan


def test_payment_month_is_stored_as_the_first_of_the_month(client, db_session):
    _, user, loan = _fixture(db_session, disbursement_date=date(2026, 1, 1))
    this_month = date.today().replace(day=1)

    response = _submit(client, user, loan, payment_month=this_month.strftime("%Y-%m"))

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["payment_month"] == this_month.isoformat()
    stored = db_session.query(models.LoanRepayment).filter(models.LoanRepayment.id == body["id"]).one()
    assert stored.payment_month == this_month


def test_payment_month_is_required(client, db_session):
    _, user, loan = _fixture(db_session)
    payload = {
        "amount_claimed": "10000.00",
        "payment_reference": "TRF-NO-MONTH",
        "receipt_image_base64": "aGVsbG8=",
        "receipt_content_type": "image/png",
    }

    response = client.post(
        f"/api/loans/{loan.id}/repayments", headers=auth_headers(user), json=payload
    )

    assert response.status_code == 422
    assert "payment_month" in response.text


def test_payment_month_must_be_a_month_label(client, db_session):
    _, user, loan = _fixture(db_session)

    response = _submit(client, user, loan, payment_month="2026-11-04")

    assert response.status_code == 422
    assert "YYYY-MM" in response.text


def test_future_payment_month_is_refused(client, db_session):
    _, user, loan = _fixture(db_session)
    today = date.today()
    future = date(today.year + 1, today.month, 1)

    response = _submit(client, user, loan, payment_month=future.strftime("%Y-%m"))

    assert response.status_code == 400
    assert "future" in response.json()["detail"]


def test_payment_month_before_disbursement_is_refused(client, db_session):
    _, user, loan = _fixture(db_session, disbursement_date=date.today().replace(day=1))
    previous = date(
        loan.disbursement_date.year - 1 if loan.disbursement_date.month == 1 else loan.disbursement_date.year,
        12 if loan.disbursement_date.month == 1 else loan.disbursement_date.month - 1,
        1,
    )

    response = _submit(client, user, loan, payment_month=previous.strftime("%Y-%m"))

    assert response.status_code == 400
    assert "disbursed" in response.json()["detail"]


def test_legacy_repayments_keep_a_null_month(client, db_session):
    member, user, loan = _fixture(db_session, disbursement_date=date(2026, 1, 1))
    legacy = models.LoanRepayment(
        loan_id=loan.id,
        member_id=member.id,
        amount_claimed=Decimal("10000.00"),
        payment_reference="TRF-LEGACY",
        receipt_image_base64="aGVsbG8=",
        receipt_content_type="image/png",
        status=models.RepaymentVerificationStatus.VERIFIED,
    )
    db_session.add(legacy)
    db_session.commit()

    response = client.get(f"/api/loans/{loan.id}/repayments", headers=auth_headers(user))

    assert response.status_code == 200
    assert response.json()[0]["payment_month"] is None