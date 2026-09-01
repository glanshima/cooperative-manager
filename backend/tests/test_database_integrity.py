from decimal import Decimal

from sqlalchemy.exc import IntegrityError

from tests.conftest import auth_headers, grant_permission, make_admin_user, make_member


def test_loan_negative_principal_rejected_by_db_constraint(db_session, seed_permissions):
    """Phase 1 remediation, Section 6: DB-level CHECK constraints are a
    defense-in-depth backstop even when the API-level Pydantic validation
    is bypassed (e.g. a direct insert)."""
    from app import models

    loan_type = models.LoanType(name="Negative Principal Test Loan", is_active=True)
    db_session.add(loan_type)
    db_session.commit()

    member = make_member(db_session, psn="DBCONS-001", email="dbcons1@example.com")

    bad_loan = models.Loan(
        member_id=member.id,
        loan_type_id=loan_type.id,
        principal=Decimal("-100"),
        interest_amount=Decimal("0"),
        net_disbursed=Decimal("0"),
        total_repayable=Decimal("100"),
        monthly_installment=Decimal("10"),
        disbursement_date="2026-01-01",
        expected_end_date="2026-07-01",
        amount_repaid=Decimal("0"),
        status=models.LoanStatus.ACTIVE,
    )
    db_session.add(bad_loan)
    try:
        db_session.commit()
        assert False, "Expected the DB CHECK constraint to reject a negative principal"
    except IntegrityError:
        db_session.rollback()


def test_loan_repayment_zero_amount_rejected_by_db_constraint(db_session, seed_permissions):
    from app import models

    loan_type = models.LoanType(name="Zero Repayment Test Loan", is_active=True)
    db_session.add(loan_type)
    db_session.commit()

    member = make_member(db_session, psn="DBCONS-002", email="dbcons2@example.com")
    loan = models.Loan(
        member_id=member.id,
        loan_type_id=loan_type.id,
        principal=Decimal("1000"),
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

    bad_repayment = models.LoanRepayment(
        loan_id=loan.id,
        member_id=member.id,
        amount_claimed=Decimal("0"),
        payment_reference="ref-zero",
        receipt_image_base64="aGVsbG8=",
        receipt_content_type="image/png",
    )
    db_session.add(bad_repayment)
    try:
        db_session.commit()
        assert False, "Expected the DB CHECK constraint to reject a zero amount_claimed"
    except IntegrityError:
        db_session.rollback()


def test_duplicate_psn_rejected(client, db_session, seed_permissions):
    admin = make_admin_user(db_session, username="dup_psn_admin")
    grant_permission(db_session, admin, "member.create")

    # next_of_kin_is_member is required as of the Member Relationship /
    # Next-of-Kin Controlled Remediation (2026-09) -- see schemas.py's
    # MemberCreate docstring for why this is an intentional break for
    # any caller that predates it, not a regression to work around.
    payload = {"psn": "DUP-001", "name": "First Member", "next_of_kin_is_member": False}
    res1 = client.post("/api/members", json=payload, headers=auth_headers(admin))
    assert res1.status_code == 201

    res2 = client.post(
        "/api/members",
        json={"psn": "DUP-001", "name": "Second Member", "next_of_kin_is_member": False},
        headers=auth_headers(admin),
    )
    assert res2.status_code == 409


def test_duplicate_admin_username_rejected(client, db_session, seed_permissions):
    admin = make_admin_user(db_session, username="dup_user_admin")
    grant_permission(db_session, admin, "admin.user_manage")

    res1 = client.post(
        "/api/admin/users",
        json={"username": "shared-name", "password": "Passw0rd!"},
        headers=auth_headers(admin),
    )
    assert res1.status_code == 201

    res2 = client.post(
        "/api/admin/users",
        json={"username": "shared-name", "password": "Passw0rd!"},
        headers=auth_headers(admin),
    )
    assert res2.status_code == 409


def test_member_with_loan_history_cannot_be_hard_deleted(client, db_session, seed_permissions):
    from app import models

    admin = make_admin_user(db_session, username="delete_admin")
    grant_permission(db_session, admin, "member.deactivate")

    member = make_member(db_session, psn="DEL-001", email="del1@example.com")
    loan_type = models.LoanType(name="Delete Test Loan", is_active=True)
    db_session.add(loan_type)
    db_session.commit()

    loan = models.Loan(
        member_id=member.id,
        loan_type_id=loan_type.id,
        principal=1000,
        interest_amount=100,
        net_disbursed=900,
        total_repayable=1100,
        monthly_installment=200,
        disbursement_date="2026-01-01",
        expected_end_date="2026-07-01",
        amount_repaid=0,
        status=models.LoanStatus.ACTIVE,
    )
    db_session.add(loan)
    db_session.commit()

    res = client.delete(f"/api/members/{member.id}", headers=auth_headers(admin))
    assert res.status_code == 409

    still_there = db_session.query(models.Member).filter(models.Member.id == member.id).first()
    assert still_there is not None


def test_member_without_loan_history_can_be_deleted(client, db_session, seed_permissions):
    admin = make_admin_user(db_session, username="delete_clean_admin")
    grant_permission(db_session, admin, "member.deactivate")
    member = make_member(db_session, psn="DEL-002", email="del2@example.com")

    res = client.delete(f"/api/members/{member.id}", headers=auth_headers(admin))
    assert res.status_code == 204


def test_loan_cannot_be_deleted_at_all(client, db_session, seed_permissions):
    """Loans are posted financial records -- Section 15/16. See
    Change-Control C-3 in the Phase 1 implementation report."""
    from app import models

    admin = make_admin_user(db_session, username="loan_delete_admin", super_admin=True)
    member = make_member(db_session, psn="DEL-003", email="del3@example.com")
    loan_type = models.LoanType(name="Non-deletable Loan", is_active=True)
    db_session.add(loan_type)
    db_session.commit()

    loan = models.Loan(
        member_id=member.id,
        loan_type_id=loan_type.id,
        principal=1000,
        interest_amount=100,
        net_disbursed=900,
        total_repayable=1100,
        monthly_installment=200,
        disbursement_date="2026-01-01",
        expected_end_date="2026-07-01",
        amount_repaid=0,
        status=models.LoanStatus.ACTIVE,
    )
    db_session.add(loan)
    db_session.commit()
    db_session.refresh(loan)

    res = client.delete(f"/api/loans/{loan.id}", headers=auth_headers(admin))
    assert res.status_code == 409
