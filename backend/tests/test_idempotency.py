from datetime import datetime, timedelta
from decimal import Decimal

from tests.conftest import auth_headers, grant_permission, make_admin_user, make_member, make_member_user


def _make_active_loan(db_session, member, principal=Decimal("1000")):
    from app import models

    loan_type = models.LoanType(name="Idempotency Test Loan", is_active=True)
    db_session.add(loan_type)
    db_session.commit()

    loan = models.Loan(
        member_id=member.id,
        loan_type_id=loan_type.id,
        principal=principal,
        interest_amount=Decimal("100"),
        net_disbursed=Decimal("900"),
        total_repayable=Decimal("1100"),
        monthly_installment=Decimal("200"),
        disbursement_date="2026-01-01",
        expected_end_date="2026-07-01",
        amount_repaid=Decimal("0"),
        status=models.LoanStatus.ACTIVE,
    )
    db_session.add(loan)
    db_session.commit()
    db_session.refresh(loan)
    return loan


def test_repeated_repayment_verification_with_same_key_does_not_double_credit(
    client, db_session, seed_permissions
):
    from app import models

    member = make_member(db_session, psn="IDEM-001", email="idem1@example.com")
    member_user = make_member_user(db_session, member)
    admin = make_admin_user(db_session, username="idem_verify_admin")
    grant_permission(db_session, admin, "repayment.verify")

    loan = _make_active_loan(db_session, member)

    repayment = models.LoanRepayment(
        loan_id=loan.id,
        member_id=member.id,
        amount_claimed=Decimal("200"),
        payment_reference="ref-idem-1",
        receipt_image_base64="aGVsbG8=",
        receipt_content_type="image/png",
    )
    db_session.add(repayment)
    db_session.commit()
    db_session.refresh(repayment)

    headers = {**auth_headers(admin), "Idempotency-Key": "verify-once-key-1"}
    res1 = client.post(
        f"/api/loan-repayments/{repayment.id}/verify",
        json={"approved": True},
        headers=headers,
    )
    assert res1.status_code == 200

    res2 = client.post(
        f"/api/loan-repayments/{repayment.id}/verify",
        json={"approved": True},
        headers=headers,
    )
    # Second call with the same key must not re-execute -- the loan's
    # amount_repaid must reflect exactly ONE credit, not two.
    assert res2.status_code == 200

    db_session.refresh(loan)
    assert loan.amount_repaid == Decimal("200")


def test_mismatched_body_with_reused_key_is_rejected(client, db_session, seed_permissions):
    from app import models

    member = make_member(db_session, psn="IDEM-002", email="idem2@example.com")
    admin = make_admin_user(db_session, username="idem_mismatch_admin")
    grant_permission(db_session, admin, "repayment.verify")

    loan = _make_active_loan(db_session, member)
    repayment = models.LoanRepayment(
        loan_id=loan.id,
        member_id=member.id,
        amount_claimed=Decimal("150"),
        payment_reference="ref-idem-2",
        receipt_image_base64="aGVsbG8=",
        receipt_content_type="image/png",
    )
    db_session.add(repayment)
    db_session.commit()
    db_session.refresh(repayment)

    headers = {**auth_headers(admin), "Idempotency-Key": "reused-key"}
    res1 = client.post(
        f"/api/loan-repayments/{repayment.id}/verify", json={"approved": False, "rejection_reason": "x"}, headers=headers
    )
    assert res1.status_code == 200

    # Same key, DIFFERENT body -- must be rejected, not silently run.
    res2 = client.post(
        f"/api/loan-repayments/{repayment.id}/verify", json={"approved": True}, headers=headers
    )
    assert res2.status_code == 409


def test_already_reviewed_repayment_cannot_be_reverified_without_idempotency_key(
    client, db_session, seed_permissions
):
    """Without an Idempotency-Key at all, the underlying status-check
    protection (Section 18 row locking + status guard) still applies:
    verifying an already-verified repayment is rejected outright."""
    from app import models

    member = make_member(db_session, psn="IDEM-003", email="idem3@example.com")
    admin = make_admin_user(db_session, username="idem_status_admin")
    grant_permission(db_session, admin, "repayment.verify")

    loan = _make_active_loan(db_session, member)
    repayment = models.LoanRepayment(
        loan_id=loan.id,
        member_id=member.id,
        amount_claimed=Decimal("100"),
        payment_reference="ref-idem-3",
        receipt_image_base64="aGVsbG8=",
        receipt_content_type="image/png",
    )
    db_session.add(repayment)
    db_session.commit()
    db_session.refresh(repayment)

    headers = auth_headers(admin)
    res1 = client.post(
        f"/api/loan-repayments/{repayment.id}/verify", json={"approved": True}, headers=headers
    )
    assert res1.status_code == 200

    res2 = client.post(
        f"/api/loan-repayments/{repayment.id}/verify", json={"approved": True}, headers=headers
    )
    assert res2.status_code == 400


def test_concurrent_duplicate_request_is_rejected_not_double_executed(
    client, db_session, seed_permissions
):
    """Phase 1 remediation, Section 4 item 3: simulate the race where a
    second request arrives while the first, using the same Idempotency-Key,
    has not finished yet. Rather than both proceeding to execute the
    financial operation, the second request must be rejected with 409
    while a reservation is still pending."""
    from app import models
    from app.idempotency import idempotency_check  # noqa: F401 -- documents what's under test

    member = make_member(db_session, psn="IDEM-004", email="idem4@example.com")
    admin = make_admin_user(db_session, username="idem_race_admin")
    grant_permission(db_session, admin, "repayment.verify")

    loan = _make_active_loan(db_session, member)
    repayment = models.LoanRepayment(
        loan_id=loan.id,
        member_id=member.id,
        amount_claimed=Decimal("50"),
        payment_reference="ref-idem-race",
        receipt_image_base64="aGVsbG8=",
        receipt_content_type="image/png",
    )
    db_session.add(repayment)
    db_session.commit()
    db_session.refresh(repayment)

    # Manually reserve the key the same way idempotency_check() would on
    # the "first" concurrent request, without completing it -- this
    # stands in for "another request is still mid-flight".
    reservation = models.IdempotencyRecord(
        user_id=admin.id,
        endpoint=f"POST /api/loan-repayments/{repayment.id}/verify",
        idempotency_key="race-key-1",
        request_hash="__will_not_match_body_hash_isnt_checked_first__",
    )
    db_session.add(reservation)
    db_session.commit()

    # The pending reservation's hash won't match this request's actual
    # body hash, so the assertion here really just needs the endpoint to
    # NOT execute the financial operation -- the concurrency behavior is
    # exercised more directly at the idempotency.py unit level, but this
    # confirms no double-credit happens through the real HTTP path when a
    # pending record for the same key already exists.
    headers = {**auth_headers(admin), "Idempotency-Key": "race-key-1"}
    res = client.post(
        f"/api/loan-repayments/{repayment.id}/verify",
        json={"approved": True},
        headers=headers,
    )
    assert res.status_code == 409

    db_session.refresh(loan)
    assert loan.amount_repaid == Decimal("0")


def test_stale_pending_reservation_can_be_reclaimed(client, db_session, seed_permissions):
    """Section 4 item 5: replay after FAILED completion must not
    permanently lock a key out. A pending reservation older than
    PENDING_RECORD_STALE_SECONDS is treated as an abandoned/crashed
    attempt and the key becomes usable again."""
    from app import models
    from app.idempotency import PENDING_RECORD_STALE_SECONDS

    member = make_member(db_session, psn="IDEM-005", email="idem5@example.com")
    admin = make_admin_user(db_session, username="idem_stale_admin")
    grant_permission(db_session, admin, "repayment.verify")

    loan = _make_active_loan(db_session, member)
    repayment = models.LoanRepayment(
        loan_id=loan.id,
        member_id=member.id,
        amount_claimed=Decimal("75"),
        payment_reference="ref-idem-stale",
        receipt_image_base64="aGVsbG8=",
        receipt_content_type="image/png",
    )
    db_session.add(repayment)
    db_session.commit()
    db_session.refresh(repayment)

    stale_reservation = models.IdempotencyRecord(
        user_id=admin.id,
        endpoint=f"POST /api/loan-repayments/{repayment.id}/verify",
        idempotency_key="stale-key-1",
        request_hash="irrelevant",
        created_at=datetime.utcnow() - timedelta(seconds=PENDING_RECORD_STALE_SECONDS + 5),
    )
    db_session.add(stale_reservation)
    db_session.commit()

    headers = {**auth_headers(admin), "Idempotency-Key": "stale-key-1"}
    res = client.post(
        f"/api/loan-repayments/{repayment.id}/verify",
        json={"approved": True},
        headers=headers,
    )
    assert res.status_code == 200
    db_session.refresh(loan)
    assert loan.amount_repaid == Decimal("75")
