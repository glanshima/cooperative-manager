"""A member may hold at most one ACTIVE loan per loan type at a time."""
from datetime import date
from decimal import Decimal

from app import models
from tests.conftest import auth_headers, make_admin_user, make_loan_type, make_member


def _loan_payload(member, loan_type, principal="1000.00"):
    return {
        "member_id": str(member.id),
        "loan_type_id": str(loan_type.id),
        "principal": principal,
        "disbursement_date": "2026-11-01",
    }


def _make_loan(db_session, member, loan_type, *, status=models.LoanStatus.ACTIVE):
    loan = models.Loan(
        member_id=member.id,
        loan_type_id=loan_type.id,
        principal=Decimal("1000.00"),
        interest_amount=Decimal("0.00"),
        net_disbursed=Decimal("1000.00"),
        total_repayable=Decimal("1000.00"),
        monthly_installment=Decimal("100.00"),
        disbursement_date=date(2026, 1, 1),
        expected_end_date=date(2027, 1, 1),
        amount_repaid=Decimal("0.00"),
        status=status,
    )
    db_session.add(loan)
    db_session.commit()
    db_session.refresh(loan)
    return loan


def test_direct_disbursement_blocks_second_active_loan_of_same_type(client, db_session):
    admin = make_admin_user(db_session, username="loan_unique", super_admin=True)
    member = make_member(db_session, psn="PSN-UNIQ-1", email="uniq1@example.com")
    capital = make_loan_type(db_session, "Capital Loan")
    quick = make_loan_type(db_session, "Quick Loan")

    first = client.post(
        "/api/loans", headers=auth_headers(admin), json=_loan_payload(member, capital)
    )
    assert first.status_code == 201, first.text

    duplicate = client.post(
        "/api/loans", headers=auth_headers(admin), json=_loan_payload(member, capital)
    )
    assert duplicate.status_code == 409
    assert "already has an active" in duplicate.json()["detail"]

    # A different loan type is still allowed concurrently.
    other_type = client.post(
        "/api/loans", headers=auth_headers(admin), json=_loan_payload(member, quick)
    )
    assert other_type.status_code == 201, other_type.text


def test_update_cannot_reactivate_a_loan_when_another_of_that_type_is_active(
    client, db_session
):
    admin = make_admin_user(db_session, username="loan_reactivate", super_admin=True)
    member = make_member(db_session, psn="PSN-UNIQ-2", email="uniq2@example.com")
    loan_type = make_loan_type(db_session, "Capital Loan")

    _make_loan(db_session, member, loan_type, status=models.LoanStatus.ACTIVE)
    second = _make_loan(db_session, member, loan_type, status=models.LoanStatus.COMPLETED)

    res = client.put(
        f"/api/loans/{second.id}",
        headers=auth_headers(admin),
        json={"status": "active"},
    )
    assert res.status_code == 409
    assert "already has an active" in res.json()["detail"]

    db_session.expire_all()
    unchanged = db_session.query(models.Loan).filter(models.Loan.id == second.id).one()
    assert unchanged.status == models.LoanStatus.COMPLETED
