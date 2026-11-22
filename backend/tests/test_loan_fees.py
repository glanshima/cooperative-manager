"""The loan processing fee is paid separately (2026-11).

The fee is cooperative income: it is NOT deducted from the payout, NOT
added to total_repayable and NOT part of any instalment. loans.fee_amount
records what is owed; loan_fee_payments is the verified proof ledger a
future cashbook will report.
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
    make_member_user,
)


def _make_loan(db_session, member, loan_type, *, fee="50.00", status=models.LoanStatus.ACTIVE):
    loan = models.Loan(
        member_id=member.id,
        loan_type_id=loan_type.id,
        principal=Decimal("1000.00"),
        interest_amount=Decimal("0.00"),
        net_disbursed=Decimal("1000.00"),
        total_repayable=Decimal("1000.00"),
        monthly_installment=Decimal("100.00"),
        fee_amount=Decimal(fee),
        disbursement_date=date(2026, 1, 1),
        expected_end_date=date(2027, 1, 1),
        amount_repaid=Decimal("0.00"),
        status=status,
    )
    db_session.add(loan)
    db_session.commit()
    db_session.refresh(loan)
    return loan


def _submit(client, user, loan, **overrides):
    payload = {
        "payment_reference": "TRF-FEE-1",
        "receipt_image_base64": "aGVsbG8=",
        "receipt_content_type": "image/png",
    }
    payload.update(overrides)
    return client.post(f"/api/loans/{loan.id}/fee-payment", headers=auth_headers(user), json=payload)


def _fixture(db_session, psn="PSN-FEE", fee="50.00"):
    member = make_member(db_session, psn=psn, name="Fee Member", email=f"{psn.lower()}@example.com")
    user = make_member_user(db_session, member)
    loan_type = make_loan_type(db_session, f"Fee Loan {psn}", flat_charge=Decimal(fee))
    loan = _make_loan(db_session, member, loan_type, fee=fee)
    return member, user, loan


def _verifier(db_session, username="fee_verifier"):
    admin = make_admin_user(db_session, username=username)
    grant_permission(db_session, admin, "loan.fee_verify", "loan.view")
    return admin


def test_member_submits_the_fee_owed_on_the_loan(client, db_session, seed_permissions):
    member, user, loan = _fixture(db_session)

    response = _submit(client, user, loan)

    assert response.status_code == 201, response.text
    body = response.json()
    assert Decimal(body["amount"]) == Decimal("50.00")
    assert body["status"] == "awaiting_verification"
    assert body["member_id"] == str(member.id)


def test_a_loan_without_a_fee_cannot_receive_a_payment(client, db_session, seed_permissions):
    member, user, loan = _fixture(db_session, psn="PSN-FEE-ZERO", fee="0.00")

    response = _submit(client, user, loan)

    assert response.status_code == 400
    assert "no fee" in response.json()["detail"]


def test_member_cannot_pay_another_members_fee(client, db_session, seed_permissions):
    _, _, loan = _fixture(db_session, psn="PSN-FEE-A")
    other = make_member(db_session, psn="PSN-FEE-B", email="feeb@example.com")
    other_user = make_member_user(db_session, other)

    response = _submit(client, other_user, loan)

    assert response.status_code == 403


def test_only_one_fee_payment_can_be_open_at_a_time(client, db_session, seed_permissions):
    _, user, loan = _fixture(db_session)

    assert _submit(client, user, loan).status_code == 201
    second = _submit(client, user, loan, payment_reference="TRF-FEE-2")

    assert second.status_code == 400
    assert "awaiting review" in second.json()["detail"]


def test_verification_marks_the_fee_paid_and_leaves_the_loan_untouched(
    client, db_session, seed_permissions
):
    _, user, loan = _fixture(db_session)
    admin = _verifier(db_session)
    submitted = _submit(client, user, loan).json()

    response = client.post(
        f"/api/loan-fees/{submitted['id']}/verify",
        headers=auth_headers(admin),
        json={"approved": True},
    )

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "verified"

    db_session.expire_all()
    stored_loan = db_session.query(models.Loan).filter(models.Loan.id == loan.id).one()
    # The fee is income, not a repayment: balances stay exactly as they were.
    assert stored_loan.total_repayable == Decimal("1000.00")
    assert stored_loan.amount_repaid == Decimal("0.00")
    assert stored_loan.net_disbursed == Decimal("1000.00")
    assert stored_loan.status == models.LoanStatus.ACTIVE

    queue = client.get("/api/loan-fees", headers=auth_headers(admin))
    assert queue.status_code == 200
    assert queue.json()[0]["status"] == "verified"

    duplicate = client.post(
        f"/api/loan-fees/{submitted['id']}/verify",
        headers=auth_headers(admin),
        json={"approved": True},
    )
    assert duplicate.status_code == 400
    assert "already been reviewed" in duplicate.json()["detail"]


def test_paid_loan_reports_fee_paid_and_refuses_another_submission(
    client, db_session, seed_permissions
):
    _, user, loan = _fixture(db_session)
    admin = _verifier(db_session)
    submitted = _submit(client, user, loan).json()
    client.post(
        f"/api/loan-fees/{submitted['id']}/verify",
        headers=auth_headers(admin),
        json={"approved": True},
    )

    detail = client.get(f"/api/loans/{loan.id}", headers=auth_headers(user))
    assert detail.status_code == 200
    assert detail.json()["fee_status"] == "paid"

    again = _submit(client, user, loan, payment_reference="TRF-FEE-AGAIN")
    assert again.status_code == 400
    assert "already been paid" in again.json()["detail"]


def test_rejection_requires_a_reason_and_records_it(client, db_session, seed_permissions):
    _, user, loan = _fixture(db_session)
    admin = _verifier(db_session)
    submitted = _submit(client, user, loan).json()

    missing = client.post(
        f"/api/loan-fees/{submitted['id']}/verify",
        headers=auth_headers(admin),
        json={"approved": False},
    )
    assert missing.status_code == 400

    rejected = client.post(
        f"/api/loan-fees/{submitted['id']}/verify",
        headers=auth_headers(admin),
        json={"approved": False, "rejection_reason": "Receipt is unreadable"},
    )
    assert rejected.status_code == 200, rejected.text
    assert rejected.json()["status"] == "rejected"
    assert rejected.json()["rejection_reason"] == "Receipt is unreadable"

    detail = client.get(f"/api/loans/{loan.id}", headers=auth_headers(user)).json()
    assert detail["fee_status"] == "rejected"
    assert detail["fee_rejection_reason"] == "Receipt is unreadable"


def test_verify_needs_the_fee_permission(client, db_session, seed_permissions):
    _, user, loan = _fixture(db_session)
    plain_admin = make_admin_user(db_session, username="fee_no_perm")
    grant_permission(db_session, plain_admin, "loan.view")
    submitted = _submit(client, user, loan).json()

    response = client.post(
        f"/api/loan-fees/{submitted['id']}/verify",
        headers=auth_headers(plain_admin),
        json={"approved": True},
    )

    assert response.status_code == 403
    assert "loan.fee_verify" in response.json()["detail"]


def test_conflicted_officer_cannot_verify_a_related_members_fee(
    client, db_session, seed_permissions
):
    _, user, loan = _fixture(db_session)
    submitted = _submit(client, user, loan).json()

    own_member = make_member(db_session, psn="PSN-FEE-OWN", email="feeown@example.com")
    conflicted_admin = make_admin_user(
        db_session, username="fee_conflicted", member_id=own_member.id
    )
    grant_permission(db_session, conflicted_admin, "loan.fee_verify", "loan.view")
    db_session.add(
        models.MemberRelationship(
            member_id=own_member.id,
            related_member_id=loan.member_id,
            conflict_of_interest=True,
            status=models.RelationshipStatus.ACTIVE,
        )
    )
    db_session.commit()

    response = client.post(
        f"/api/loan-fees/{submitted['id']}/verify",
        headers=auth_headers(conflicted_admin),
        json={"approved": True},
    )

    assert response.status_code == 409
    assert response.json()["detail"]["error"] == "member_conflict"

    db_session.expire_all()
    still_open = (
        db_session.query(models.LoanFeePayment)
        .filter(models.LoanFeePayment.id == submitted["id"])
        .one()
    )
    assert still_open.status == models.FeePaymentStatus.AWAITING_VERIFICATION
