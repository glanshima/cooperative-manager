"""The loan processing fee is paid separately (2026-11).

The fee is cooperative income: it is NOT deducted from the payout, NOT
added to total_repayable and NOT part of any instalment. loans.fee_amount
records what is owed; loan_fee_payments is the verified proof ledger a
future cashbook will report.
"""
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from decimal import Decimal
from threading import Barrier
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app import models
from app.main import app
from app.routers import loan_fees
from tests.conftest import (
    TestSessionLocal,
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


def test_application_paid_loan_cannot_verify_an_old_second_fee_payment(
    client, db_session, seed_permissions
):
    _, _, loan = _fixture(db_session, psn="PSN-FEE-APP-PAID")
    loan.fee_paid_via_application = True
    db_session.commit()
    admin = _verifier(db_session)
    payment = models.LoanFeePayment(
        loan_id=loan.id,
        member_id=loan.member_id,
        amount=loan.fee_amount,
        payment_reference="TRF-LEGACY-SECOND-FEE",
        receipt_image_base64="aGVsbG8=",
        receipt_content_type="image/png",
        status=models.FeePaymentStatus.AWAITING_VERIFICATION,
    )
    db_session.add(payment)
    db_session.commit()
    db_session.refresh(payment)

    blocked = client.post(
        f"/api/loan-fees/{payment.id}/verify",
        headers=auth_headers(admin),
        json={"approved": True},
    )
    assert blocked.status_code == 400, blocked.text
    assert "paid with its application" in blocked.json()["detail"]
    db_session.expire_all()
    still_open = db_session.query(models.LoanFeePayment).filter(models.LoanFeePayment.id == payment.id).one()
    assert still_open.status == models.FeePaymentStatus.AWAITING_VERIFICATION

    rejected = client.post(
        f"/api/loan-fees/{payment.id}/verify",
        headers=auth_headers(admin),
        json={"approved": False, "rejection_reason": "Fee already settled with application"},
    )
    assert rejected.status_code == 200, rejected.text
    assert rejected.json()["status"] == "rejected"


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


def test_concurrent_direct_fee_requests_create_and_verify_only_one_obligation(monkeypatch):
    setup: Session = TestSessionLocal()
    suffix = uuid4().hex[:8]
    member = user = loan = admin = None
    try:
        member = make_member(
            setup,
            psn=f"PSN-FEE-RACE-{suffix}",
            email=f"fee-race-{suffix}@example.com",
        )
        user = make_member_user(setup, member)
        loan_type = make_loan_type(setup, f"Fee Race Loan {suffix}")
        loan = _make_loan(setup, member, loan_type)
        admin = make_admin_user(
            setup, username=f"fee_race_{suffix}", super_admin=True
        )

        monkeypatch.setattr(
            loan_fees.notification_service, "notify_staff", lambda *args, **kwargs: 0
        )
        monkeypatch.setattr(
            loan_fees.notification_service, "notify_member", lambda *args, **kwargs: None
        )
        monkeypatch.setattr(
            loan_fees.audit_service, "log_event", lambda *args, **kwargs: None
        )
        posting_calls = []
        post_loan_fee = loan_fees.cashbook.post_loan_fee

        def record_posting(db, payment, **kwargs):
            posting_calls.append(payment.id)
            return post_loan_fee(db, payment, **kwargs)

        monkeypatch.setattr(loan_fees.cashbook, "post_loan_fee", record_posting)

        submit_barrier = Barrier(2)

        def submit(reference):
            with TestClient(app) as test_client:
                submit_barrier.wait()
                return test_client.post(
                    f"/api/loans/{loan.id}/fee-payment",
                    headers=auth_headers(user),
                    json={
                        "payment_reference": reference,
                        "receipt_image_base64": "aGVsbG8=",
                        "receipt_content_type": "image/png",
                    },
                )

        with ThreadPoolExecutor(max_workers=2) as pool:
            submitted = list(
                pool.map(submit, [f"TRF-RACE-A-{suffix}", f"TRF-RACE-B-{suffix}"])
            )

        assert sorted(response.status_code for response in submitted) == [201, 400]
        created = next(response for response in submitted if response.status_code == 201)
        payment_id = created.json()["id"]
        setup.expire_all()
        assert (
            setup.query(models.LoanFeePayment)
            .filter(models.LoanFeePayment.loan_id == loan.id)
            .count()
            == 1
        )

        verify_barrier = Barrier(2)

        def verify(_):
            with TestClient(app) as test_client:
                verify_barrier.wait()
                return test_client.post(
                    f"/api/loan-fees/{payment_id}/verify",
                    headers=auth_headers(admin),
                    json={"approved": True},
                )

        with ThreadPoolExecutor(max_workers=2) as pool:
            verified = list(pool.map(verify, [0, 1]))

        assert sorted(response.status_code for response in verified) == [200, 400]
        setup.expire_all()
        stored = (
            setup.query(models.LoanFeePayment)
            .filter(models.LoanFeePayment.id == payment_id)
            .one()
        )
        assert stored.status == models.FeePaymentStatus.VERIFIED
        assert posting_calls == [stored.id]
    finally:
        setup.rollback()
        if loan is not None:
            setup.query(models.LoanFeePayment).filter(
                models.LoanFeePayment.loan_id == loan.id
            ).delete(synchronize_session=False)
            setup.query(models.Loan).filter(models.Loan.id == loan.id).delete(
                synchronize_session=False
            )
            setup.query(models.LoanType).filter(
                models.LoanType.id == loan.loan_type_id
            ).delete(synchronize_session=False)
        if user is not None:
            setup.query(models.User).filter(models.User.id == user.id).delete(
                synchronize_session=False
            )
        if admin is not None:
            setup.query(models.User).filter(models.User.id == admin.id).delete(
                synchronize_session=False
            )
        if member is not None:
            setup.query(models.Member).filter(models.Member.id == member.id).delete(
                synchronize_session=False
            )
        setup.commit()
        setup.close()
