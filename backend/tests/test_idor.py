from tests.conftest import auth_headers, grant_permission, make_admin_user, make_member, make_member_user


def test_member_cannot_fetch_another_members_record_by_id(client, db_session):
    member_a = make_member(db_session, psn="PSN-A", email="a@example.com")
    member_b = make_member(db_session, psn="PSN-B", email="b@example.com")
    user_a = make_member_user(db_session, member_a)

    res = client.get(f"/api/members/{member_b.id}", headers=auth_headers(user_a))
    assert res.status_code == 403


def test_member_can_fetch_own_record(client, db_session):
    member_a = make_member(db_session, psn="PSN-C", email="c@example.com")
    user_a = make_member_user(db_session, member_a)

    res = client.get(f"/api/members/{member_a.id}", headers=auth_headers(user_a))
    assert res.status_code == 200
    assert res.json()["id"] == str(member_a.id)


def test_admin_without_permission_cannot_fetch_member_by_id(client, db_session, seed_permissions):
    member = make_member(db_session, psn="PSN-D", email="d@example.com")
    admin = make_admin_user(db_session, username="idor_admin_no_perm")

    res = client.get(f"/api/members/{member.id}", headers=auth_headers(admin))
    assert res.status_code == 403


def test_member_cannot_view_another_members_loan(client, db_session):
    from app import models

    member_a = make_member(db_session, psn="PSN-E", email="e@example.com")
    member_b = make_member(db_session, psn="PSN-F", email="f@example.com")
    user_a = make_member_user(db_session, member_a)

    loan_type = models.LoanType(name="Test Loan IDOR", is_active=True)
    db_session.add(loan_type)
    db_session.commit()

    loan_b = models.Loan(
        member_id=member_b.id,
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
    db_session.add(loan_b)
    db_session.commit()
    db_session.refresh(loan_b)

    res = client.get(f"/api/loans/{loan_b.id}", headers=auth_headers(user_a))
    assert res.status_code == 403


def test_nonexistent_id_does_not_leak_existence_differently_than_forbidden(client, db_session):
    """A random, non-existent member id should 404 for an authorized
    admin (not 403/500), confirming the lookup -- not the permission
    check -- is what determines the 404."""
    import uuid

    admin = make_admin_user(db_session, username="idor_404_admin", super_admin=True)
    res = client.get(f"/api/members/{uuid.uuid4()}", headers=auth_headers(admin))
    assert res.status_code == 404
