"""Tests for PATCH /api/admin/users/{user_id}/member-link (Controlled
Phase 1 Remediation, Section 10)."""
from tests.conftest import auth_headers, grant_permission, make_admin_user, make_member


def test_admin_user_manage_can_link_admin_to_member(client, db_session, seed_permissions):
    from app import models

    manager = make_admin_user(db_session, username="link_manager_1")
    grant_permission(db_session, manager, "admin.user_manage")

    target_admin = make_admin_user(db_session, username="link_target_1")
    member = make_member(db_session, psn="LINK-001", email="link1@example.com")

    res = client.patch(
        f"/api/admin/users/{target_admin.id}/member-link",
        json={"member_id": str(member.id), "reason": "Elected Treasurer, also a member"},
        headers=auth_headers(manager),
    )
    assert res.status_code == 200
    assert res.json()["member_id"] == str(member.id)

    event = (
        db_session.query(models.AuditEvent)
        .filter(models.AuditEvent.event_type == "admin.user_member_link_changed")
        .order_by(models.AuditEvent.created_at.desc())
        .first()
    )
    assert event is not None
    assert event.entity_id == str(target_admin.id)


def test_cannot_link_two_admins_to_the_same_member(client, db_session, seed_permissions):
    manager = make_admin_user(db_session, username="link_manager_2")
    grant_permission(db_session, manager, "admin.user_manage")

    member = make_member(db_session, psn="LINK-002", email="link2@example.com")
    first_admin = make_admin_user(db_session, username="link_target_2a", member_id=member.id)
    second_admin = make_admin_user(db_session, username="link_target_2b")

    res = client.patch(
        f"/api/admin/users/{second_admin.id}/member-link",
        json={"member_id": str(member.id)},
        headers=auth_headers(manager),
    )
    assert res.status_code == 409


def test_can_clear_an_existing_member_link(client, db_session, seed_permissions):
    manager = make_admin_user(db_session, username="link_manager_3")
    grant_permission(db_session, manager, "admin.user_manage")

    member = make_member(db_session, psn="LINK-003", email="link3@example.com")
    target_admin = make_admin_user(db_session, username="link_target_3", member_id=member.id)

    res = client.patch(
        f"/api/admin/users/{target_admin.id}/member-link",
        json={"member_id": None, "reason": "No longer serving on EXCO"},
        headers=auth_headers(manager),
    )
    assert res.status_code == 200
    assert res.json()["member_id"] is None


def test_cannot_link_a_member_role_user_via_this_endpoint(client, db_session, seed_permissions):
    from tests.conftest import make_member_user

    manager = make_admin_user(db_session, username="link_manager_4")
    grant_permission(db_session, manager, "admin.user_manage")

    member = make_member(db_session, psn="LINK-004", email="link4@example.com")
    other_member = make_member(db_session, psn="LINK-005", email="link5@example.com")
    member_user = make_member_user(db_session, member)

    res = client.patch(
        f"/api/admin/users/{member_user.id}/member-link",
        json={"member_id": str(other_member.id)},
        headers=auth_headers(manager),
    )
    assert res.status_code == 400


def test_linking_requires_admin_user_manage_permission(client, db_session, seed_permissions):
    unrelated_admin = make_admin_user(db_session, username="link_no_perm")
    target_admin = make_admin_user(db_session, username="link_target_5")
    member = make_member(db_session, psn="LINK-006", email="link6@example.com")

    res = client.patch(
        f"/api/admin/users/{target_admin.id}/member-link",
        json={"member_id": str(member.id)},
        headers=auth_headers(unrelated_admin),
    )
    assert res.status_code == 403
