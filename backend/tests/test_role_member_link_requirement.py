"""
Admin Identity Governance remediation, Governance Objective 1: tests for
Role.requires_member_link enforcement (Section 12, items 6-12).
"""
from tests.conftest import auth_headers, grant_permission, make_admin_user, make_member, make_role


def _role_manager(db_session, username="rmr_manager"):
    # Two permissions: admin.role_manage gates the assignment endpoints,
    # admin.user_manage gates PATCH .../member-link (admin_users.py).
    admin = make_admin_user(db_session, username=username)
    grant_permission(db_session, admin, "admin.role_manage", "admin.user_manage")
    return admin


def _assign(client, manager, user_id, role_id):
    return client.post(
        f"/api/admin/users/{user_id}/assignments",
        json={"user_id": str(user_id), "role_id": str(role_id)},
        headers=auth_headers(manager),
    )


# ---------------------------------------------------------------------------
# 6. Unlinked user + non-member-required role -> allowed
# ---------------------------------------------------------------------------

def test_unlinked_user_can_be_assigned_a_non_member_required_role(client, db_session, seed_permissions):
    manager = _role_manager(db_session, "rmr_manager_6")
    target = make_admin_user(db_session, username="rmr_target_6")
    role = make_role(db_session, name="System Administrator", requires_member_link=False)

    res = _assign(client, manager, target.id, role.id)
    assert res.status_code == 201


# ---------------------------------------------------------------------------
# 7. Unlinked user + member-required role -> rejected
# ---------------------------------------------------------------------------

def test_unlinked_user_cannot_be_assigned_a_member_required_role(client, db_session, seed_permissions):
    manager = _role_manager(db_session, "rmr_manager_7")
    target = make_admin_user(db_session, username="rmr_target_7")
    role = make_role(db_session, name="Treasurer", requires_member_link=True)

    res = _assign(client, manager, target.id, role.id)
    assert res.status_code == 409
    body = res.json()["detail"]
    assert body["error"] == "member_link_required"

    # Confirm the assignment was NOT created.
    from app import models

    count = (
        db_session.query(models.UserRoleAssignment)
        .filter(models.UserRoleAssignment.user_id == target.id)
        .count()
    )
    assert count == 0


# ---------------------------------------------------------------------------
# 8. Linked user + member-required role -> allowed
# ---------------------------------------------------------------------------

def test_linked_user_can_be_assigned_a_member_required_role(client, db_session, seed_permissions):
    manager = _role_manager(db_session, "rmr_manager_8")
    member = make_member(db_session, psn="RMR-008", email="rmr8@example.com")
    target = make_admin_user(db_session, username="rmr_target_8", member_id=member.id)
    role = make_role(db_session, name="President", requires_member_link=True)

    res = _assign(client, manager, target.id, role.id)
    assert res.status_code == 201


# ---------------------------------------------------------------------------
# 9. Multiple roles: any one requiring linkage -> requires linkage
# ---------------------------------------------------------------------------

def test_second_member_required_role_rejected_if_still_unlinked(client, db_session, seed_permissions):
    """User already holds a non-member-required role; assigning a SECOND,
    member-required role must still be rejected while unlinked."""
    manager = _role_manager(db_session, "rmr_manager_9")
    target = make_admin_user(db_session, username="rmr_target_9")
    non_member_role = make_role(db_session, name="Auditor", requires_member_link=False)
    member_role = make_role(db_session, name="Secretary", requires_member_link=True)

    res1 = _assign(client, manager, target.id, non_member_role.id)
    assert res1.status_code == 201

    res2 = _assign(client, manager, target.id, member_role.id)
    assert res2.status_code == 409


def test_user_with_member_required_role_requires_linkage_overall(client, db_session, seed_permissions):
    """From self_conflict.py's consumer's point of view: a user holding
    a mix of roles, at least one of which requires_member_link, must be
    treated as requiring a Member link -- confirmed here by checking that
    unlinking such a user is rejected (the practical consequence of
    'requires linkage overall')."""
    manager = _role_manager(db_session, "rmr_manager_9b")
    member = make_member(db_session, psn="RMR-009B", email="rmr9b@example.com")
    target = make_admin_user(db_session, username="rmr_target_9b", member_id=member.id)
    non_member_role = make_role(db_session, name="Loan Officer", requires_member_link=False)
    member_role = make_role(db_session, name="Vice President", requires_member_link=True)

    assert _assign(client, manager, target.id, non_member_role.id).status_code == 201
    assert _assign(client, manager, target.id, member_role.id).status_code == 201

    res = client.patch(
        f"/api/admin/users/{target.id}/member-link",
        json={"member_id": None},
        headers=auth_headers(manager),
    )
    assert res.status_code == 409
    assert res.json()["detail"]["error"] == "member_link_required"


# ---------------------------------------------------------------------------
# 10. Unlink blocked when active role requires linkage
# ---------------------------------------------------------------------------

def test_unlink_rejected_when_active_role_requires_linkage(client, db_session, seed_permissions):
    manager = _role_manager(db_session, "rmr_manager_10")
    member = make_member(db_session, psn="RMR-010", email="rmr10@example.com")
    target = make_admin_user(db_session, username="rmr_target_10", member_id=member.id)
    role = make_role(db_session, name="Financial Secretary", requires_member_link=True)
    assert _assign(client, manager, target.id, role.id).status_code == 201

    res = client.patch(
        f"/api/admin/users/{target.id}/member-link",
        json={"member_id": None},
        headers=auth_headers(manager),
    )
    assert res.status_code == 409
    assert res.json()["detail"]["error"] == "member_link_required"

    from app import models

    db_session.refresh(target)
    assert target.member_id == member.id, "member_id must be unchanged after a rejected unlink"


# ---------------------------------------------------------------------------
# 11. Change role away from member-required -> unlink then allowed
# ---------------------------------------------------------------------------

def test_unlink_allowed_after_revoking_the_member_required_role(client, db_session, seed_permissions):
    manager = _role_manager(db_session, "rmr_manager_11")
    member = make_member(db_session, psn="RMR-011", email="rmr11@example.com")
    target = make_admin_user(db_session, username="rmr_target_11", member_id=member.id)
    role = make_role(db_session, name="Treasurer II", requires_member_link=True)

    assign_res = _assign(client, manager, target.id, role.id)
    assert assign_res.status_code == 201
    assignment_id = assign_res.json()["id"]

    # Unlink should be rejected while the role is active.
    blocked = client.patch(
        f"/api/admin/users/{target.id}/member-link",
        json={"member_id": None},
        headers=auth_headers(manager),
    )
    assert blocked.status_code == 409

    # Revoke the role.
    revoke_res = client.delete(
        f"/api/admin/users/{target.id}/assignments/{assignment_id}", headers=auth_headers(manager)
    )
    assert revoke_res.status_code == 204

    # Unlink should now succeed.
    allowed = client.patch(
        f"/api/admin/users/{target.id}/member-link",
        json={"member_id": None},
        headers=auth_headers(manager),
    )
    assert allowed.status_code == 200
    assert allowed.json()["member_id"] is None


# ---------------------------------------------------------------------------
# 12. Direct API call still enforced (no separate frontend-only check)
# ---------------------------------------------------------------------------

def test_direct_api_assignment_call_is_still_rejected_for_unlinked_user(client, db_session, seed_permissions):
    """Same as test 7, but framed explicitly as 'a client that skips the
    UI entirely' -- confirms enforcement is not something only the
    Admin Users page happens to respect."""
    manager = _role_manager(db_session, "rmr_manager_12")
    target = make_admin_user(db_session, username="rmr_target_12")
    role = make_role(db_session, name="President II", requires_member_link=True)

    res = client.post(
        f"/api/admin/users/{target.id}/assignments",
        json={"user_id": str(target.id), "role_id": str(role.id), "office_id": None},
        headers=auth_headers(manager),
    )
    assert res.status_code == 409


# ---------------------------------------------------------------------------
# 13. Flipping requires_member_link on an existing role (flag-flip gap)
# ---------------------------------------------------------------------------

def test_flipping_requires_member_link_rejected_while_active_assignee_is_unlinked(
    client, db_session, seed_permissions
):
    """The same invalid state must not be creatable by editing the role
    instead of assigning it: an active role cannot start requiring
    Member linkage while an unlinked account holds it."""
    manager = _role_manager(db_session, "rmr_manager_13")
    target = make_admin_user(db_session, username="rmr_target_13")
    role = make_role(db_session, name="Exco Role 13", requires_member_link=False)
    assert _assign(client, manager, target.id, role.id).status_code == 201

    res = client.put(
        f"/api/roles/{role.id}",
        json={"requires_member_link": True},
        headers=auth_headers(manager),
    )
    assert res.status_code == 409
    detail = res.json()["detail"]
    assert detail["error"] == "member_link_required"
    assert detail["unlinked_usernames"] == [target.username]

    db_session.refresh(role)
    assert role.requires_member_link is False, "rejected flip must not persist"


def test_flipping_requires_member_link_allowed_when_all_active_assignees_are_linked(
    client, db_session, seed_permissions
):
    manager = _role_manager(db_session, "rmr_manager_14")
    member = make_member(db_session, psn="RMR-014", email="rmr14@example.com")
    target = make_admin_user(db_session, username="rmr_target_14", member_id=member.id)
    role = make_role(db_session, name="Exco Role 14", requires_member_link=False)
    assert _assign(client, manager, target.id, role.id).status_code == 201

    res = client.put(
        f"/api/roles/{role.id}",
        json={"requires_member_link": True},
        headers=auth_headers(manager),
    )
    assert res.status_code == 200, res.text
    assert res.json()["requires_member_link"] is True

    db_session.refresh(role)
    assert role.requires_member_link is True


def test_flipping_requires_member_link_allowed_after_assignee_is_revoked(
    client, db_session, seed_permissions
):
    manager = _role_manager(db_session, "rmr_manager_15")
    target = make_admin_user(db_session, username="rmr_target_15")
    role = make_role(db_session, name="Exco Role 15", requires_member_link=False)
    assignment = _assign(client, manager, target.id, role.id)
    assert assignment.status_code == 201

    revoke = client.delete(
        f"/api/admin/users/{target.id}/assignments/{assignment.json()['id']}",
        headers=auth_headers(manager),
    )
    assert revoke.status_code == 204

    res = client.put(
        f"/api/roles/{role.id}",
        json={"requires_member_link": True},
        headers=auth_headers(manager),
    )
    assert res.status_code == 200, res.text
    assert res.json()["requires_member_link"] is True


# ---------------------------------------------------------------------------
# 16. Activating a dormant member-required role is covered too
# ---------------------------------------------------------------------------

def test_activating_member_required_role_rejected_while_unlinked_assignee_exists(
    client, db_session, seed_permissions
):
    """Role.is_active is part of the invariant: an inactive role doesn't
    count as 'active' for the unlink guard, so flipping it on must be
    re-validated. (The direct assignment row simulates legacy state,
    which predates assignment-time enforcement.)"""
    from app import models

    manager = _role_manager(db_session, "rmr_manager_16")
    target = make_admin_user(db_session, username="rmr_target_16")
    role = make_role(db_session, name="Dormant Exco Role 16", requires_member_link=True)
    role.is_active = False
    db_session.add(models.UserRoleAssignment(user_id=target.id, role_id=role.id))
    db_session.commit()

    res = client.put(
        f"/api/roles/{role.id}",
        json={"is_active": True},
        headers=auth_headers(manager),
    )
    assert res.status_code == 409
    assert res.json()["detail"]["error"] == "member_link_required"

    db_session.refresh(role)
    assert role.is_active is False, "rejected activation must not persist"

    # The repair path stays open: dropping the linkage requirement saves.
    repair = client.put(
        f"/api/roles/{role.id}",
        json={"requires_member_link": False},
        headers=auth_headers(manager),
    )
    assert repair.status_code == 200, repair.text
    assert repair.json()["requires_member_link"] is False

    activate = client.put(
        f"/api/roles/{role.id}",
        json={"is_active": True},
        headers=auth_headers(manager),
    )
    assert activate.status_code == 200, activate.text
    assert activate.json()["is_active"] is True
