from tests.conftest import (
    auth_headers,
    grant_permission,
    make_admin_user,
    make_member,
)


def test_endpoint_denied_without_permission(client, db_session, seed_permissions):
    admin = make_admin_user(db_session, username="no_perm_admin")
    res = client.get("/api/members", headers=auth_headers(admin))
    assert res.status_code == 403
    assert "member.view" in res.json()["detail"]


def test_endpoint_allowed_with_granted_permission(client, db_session, seed_permissions):
    admin = make_admin_user(db_session, username="has_perm_admin")
    grant_permission(db_session, admin, "member.view")
    res = client.get("/api/members", headers=auth_headers(admin))
    assert res.status_code == 200


def test_super_admin_bypasses_granular_checks(client, db_session, seed_permissions):
    admin = make_admin_user(db_session, username="super_admin_1", super_admin=True)
    res = client.get("/api/members", headers=auth_headers(admin))
    assert res.status_code == 200


def test_role_manager_can_read_permission_catalogue(client, db_session, seed_permissions):
    """Phase 1 remediation, Section 3: a user holding only admin.role_manage
    (not admin.permission_manage) must still be able to read GET
    /api/permissions -- the Roles UI's permission matrix depends on it."""
    admin = make_admin_user(db_session, username="role_manager_1")
    grant_permission(db_session, admin, "admin.role_manage")
    res = client.get("/api/permissions", headers=auth_headers(admin))
    assert res.status_code == 200
    assert len(res.json()) > 0


def test_permission_manager_can_read_permission_catalogue(client, db_session, seed_permissions):
    admin = make_admin_user(db_session, username="permission_manager_1")
    grant_permission(db_session, admin, "admin.permission_manage")
    res = client.get("/api/permissions", headers=auth_headers(admin))
    assert res.status_code == 200


def test_unrelated_permission_cannot_read_permission_catalogue(client, db_session, seed_permissions):
    admin = make_admin_user(db_session, username="unrelated_perm_admin")
    grant_permission(db_session, admin, "member.view")
    res = client.get("/api/permissions", headers=auth_headers(admin))
    assert res.status_code == 403


def test_member_cannot_reach_admin_only_endpoint(client, db_session):
    member = make_member(db_session)
    from tests.conftest import make_member_user

    user = make_member_user(db_session, member)
    res = client.get("/api/members", headers=auth_headers(user))
    assert res.status_code == 403


def test_deactivated_admin_role_assignment_change_takes_effect(client, db_session, seed_permissions):
    """Revoking a role assignment removes access immediately (no caching)."""
    admin = make_admin_user(db_session, username="revoke_test_admin")
    role = grant_permission(db_session, admin, "member.view")

    assert client.get("/api/members", headers=auth_headers(admin)).status_code == 200

    from app import models

    assignment = (
        db_session.query(models.UserRoleAssignment)
        .filter(models.UserRoleAssignment.user_id == admin.id)
        .first()
    )
    assignment.is_active = False
    db_session.commit()

    assert client.get("/api/members", headers=auth_headers(admin)).status_code == 403


def test_segregation_of_duties_approve_vs_reject(client, db_session, seed_permissions):
    """An admin granted only loan.reject must not be able to approve, and
    vice versa -- Section 12."""
    reviewer = make_admin_user(db_session, username="reject_only_admin")
    grant_permission(db_session, reviewer, "loan.review", "loan.reject")

    member = make_member(db_session)
    from app import models

    loan_type = models.LoanType(name="Test Loan", is_active=True)
    db_session.add(loan_type)
    db_session.commit()

    application = models.LoanApplication(
        member_id=member.id,
        loan_type_id=loan_type.id,
        requested_amount=1000,
        payment_reference="ref-1",
        receipt_image_base64="aGVsbG8=",
        receipt_content_type="image/png",
        payment_status=models.PaymentVerificationStatus.VERIFIED,
        status=models.LoanApplicationStatus.PENDING,
    )
    db_session.add(application)
    db_session.commit()
    db_session.refresh(application)

    # Approving must be denied -- this admin only holds loan.reject.
    res = client.post(
        f"/api/loan-applications/{application.id}/decide",
        json={"approved": True, "approved_amount": "1000", "approved_tenure_months": 6},
        headers=auth_headers(reviewer),
    )
    assert res.status_code == 403
    assert "loan.approve" in res.json()["detail"]

    # Rejecting is allowed.
    res = client.post(
        f"/api/loan-applications/{application.id}/decide",
        json={"approved": False, "admin_notes": "not eligible"},
        headers=auth_headers(reviewer),
    )
    assert res.status_code == 200
