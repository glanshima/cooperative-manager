"""Tests for Controlled Implementation -- Admin Governance & Member-Link
Enforcement (2026-08), Sections 2-4: an admin account cannot receive a
requires_member_link=True permission unless it is linked to a Member or
explicitly confirmed as a legitimate non-member account.
"""
from tests.conftest import auth_headers, make_admin_user, make_member


def _make_role_with_permissions(db_session, name, *permission_codes):
    from app import models

    role = models.Role(name=name)
    db_session.add(role)
    db_session.flush()
    for code in permission_codes:
        permission = db_session.query(models.Permission).filter(models.Permission.code == code).first()
        assert permission is not None, f"Permission {code!r} not seeded"
        db_session.add(models.RolePermission(role_id=role.id, permission_id=permission.id))
    db_session.commit()
    db_session.refresh(role)
    return role


def _manager(db_session, username="gov_manager"):
    from tests.conftest import grant_permission

    manager = make_admin_user(db_session, username=username)
    grant_permission(db_session, manager, "admin.user_manage")
    return manager


# --- assign_role gate -------------------------------------------------


def test_unlinked_unconfirmed_admin_cannot_receive_sensitive_role(client, db_session, seed_permissions):
    manager = _manager(db_session, "gov_manager_1")
    target = make_admin_user(db_session, username="gov_target_1")
    role = _make_role_with_permissions(db_session, "gov_role_1", "loan.approve")

    res = client.post(
        f"/api/admin/users/{target.id}/assignments",
        json={"user_id": str(target.id), "role_id": str(role.id)},
        headers=auth_headers(manager),
    )
    assert res.status_code == 409
    assert "loan.approve" in res.json()["detail"]


def test_linked_admin_can_receive_sensitive_role(client, db_session, seed_permissions):
    manager = _manager(db_session, "gov_manager_2")
    member = make_member(db_session, psn="GOV-002", email="gov2@example.com")
    target = make_admin_user(db_session, username="gov_target_2", member_id=member.id)
    role = _make_role_with_permissions(db_session, "gov_role_2", "loan.approve")

    res = client.post(
        f"/api/admin/users/{target.id}/assignments",
        json={"user_id": str(target.id), "role_id": str(role.id)},
        headers=auth_headers(manager),
    )
    assert res.status_code == 201


def test_confirmed_non_member_admin_can_receive_sensitive_role(client, db_session, seed_permissions):
    manager = _manager(db_session, "gov_manager_3")
    target = make_admin_user(db_session, username="gov_target_3", confirmed_non_member_admin=True)
    role = _make_role_with_permissions(db_session, "gov_role_3", "disbursement.submit")

    res = client.post(
        f"/api/admin/users/{target.id}/assignments",
        json={"user_id": str(target.id), "role_id": str(role.id)},
        headers=auth_headers(manager),
    )
    assert res.status_code == 201


def test_non_sensitive_role_does_not_require_link(client, db_session, seed_permissions):
    manager = _manager(db_session, "gov_manager_4")
    target = make_admin_user(db_session, username="gov_target_4")
    role = _make_role_with_permissions(db_session, "gov_role_4", "member.view", "report.member")

    res = client.post(
        f"/api/admin/users/{target.id}/assignments",
        json={"user_id": str(target.id), "role_id": str(role.id)},
        headers=auth_headers(manager),
    )
    assert res.status_code == 201


# --- non-member confirmation endpoint ----------------------------------


def test_manager_can_confirm_non_member_admin(client, db_session, seed_permissions):
    from app import models

    manager = _manager(db_session, "gov_manager_5")
    target = make_admin_user(db_session, username="gov_target_5")

    res = client.patch(
        f"/api/admin/users/{target.id}/non-member-confirmation",
        json={"confirmed": True, "reason": "Hired bookkeeper, not a cooperative member"},
        headers=auth_headers(manager),
    )
    assert res.status_code == 200
    assert res.json()["confirmed_non_member_admin"] is True

    event = (
        db_session.query(models.AuditEvent)
        .filter(models.AuditEvent.event_type == "admin.user_non_member_confirmation_changed")
        .order_by(models.AuditEvent.timestamp.desc())
        .first()
    )
    assert event is not None
    assert event.entity_id == str(target.id)


def test_cannot_confirm_non_member_on_an_already_linked_account(client, db_session, seed_permissions):
    manager = _manager(db_session, "gov_manager_6")
    member = make_member(db_session, psn="GOV-006", email="gov6@example.com")
    target = make_admin_user(db_session, username="gov_target_6", member_id=member.id)

    res = client.patch(
        f"/api/admin/users/{target.id}/non-member-confirmation",
        json={"confirmed": True},
        headers=auth_headers(manager),
    )
    assert res.status_code == 400


def test_non_member_confirmation_requires_admin_user_manage_permission(client, db_session, seed_permissions):
    unrelated_admin = make_admin_user(db_session, username="gov_no_perm")
    target = make_admin_user(db_session, username="gov_target_7")

    res = client.patch(
        f"/api/admin/users/{target.id}/non-member-confirmation",
        json={"confirmed": True},
        headers=auth_headers(unrelated_admin),
    )
    assert res.status_code == 403


# --- update_role gate (second bypass path) -----------------------------


def test_cannot_add_sensitive_permission_to_role_already_held_by_unlinked_admin(
    client, db_session, seed_permissions
):
    from tests.conftest import grant_permission

    manager = _manager(db_session, "gov_manager_8")
    grant_permission(db_session, manager, "admin.role_manage", role_name="gov_role_manage_8")

    target = make_admin_user(db_session, username="gov_target_8")
    role = _make_role_with_permissions(db_session, "gov_role_8", "member.view")

    # Assign the (currently non-sensitive) role directly at the DB level,
    # bypassing the assign_role gate, to set up the "already assigned"
    # precondition this test needs.
    from app import models

    db_session.add(models.UserRoleAssignment(user_id=target.id, role_id=role.id))
    db_session.commit()

    res = client.put(
        f"/api/roles/{role.id}",
        json={"permission_codes": ["member.view", "loan.approve"]},
        headers=auth_headers(manager),
    )
    assert res.status_code == 409


def test_can_add_sensitive_permission_to_role_held_only_by_linked_admins(
    client, db_session, seed_permissions
):
    from tests.conftest import grant_permission
    from app import models

    manager = _manager(db_session, "gov_manager_9")
    grant_permission(db_session, manager, "admin.role_manage", role_name="gov_role_manage_9")

    member = make_member(db_session, psn="GOV-009", email="gov9@example.com")
    target = make_admin_user(db_session, username="gov_target_9", member_id=member.id)
    role = _make_role_with_permissions(db_session, "gov_role_9", "member.view")

    db_session.add(models.UserRoleAssignment(user_id=target.id, role_id=role.id))
    db_session.commit()

    res = client.put(
        f"/api/roles/{role.id}",
        json={"permission_codes": ["member.view", "loan.approve"]},
        headers=auth_headers(manager),
    )
    assert res.status_code == 200
