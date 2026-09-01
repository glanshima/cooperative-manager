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


def test_linking_to_a_nonexistent_member_is_rejected(client, db_session, seed_permissions):
    manager = make_admin_user(db_session, username="link_manager_6")
    grant_permission(db_session, manager, "admin.user_manage")
    target_admin = make_admin_user(db_session, username="link_target_6")

    res = client.patch(
        f"/api/admin/users/{target_admin.id}/member-link",
        json={"member_id": "00000000-0000-0000-0000-000000000000"},
        headers=auth_headers(manager),
    )
    assert res.status_code == 404


def test_changing_an_existing_link_to_a_different_member_succeeds(client, db_session, seed_permissions):
    """Exercises the Admin Users UI's 'Change Member' action -- re-linking
    an already-linked admin to a different member (not unlink-then-relink,
    a single call with a new member_id)."""
    manager = make_admin_user(db_session, username="link_manager_7")
    grant_permission(db_session, manager, "admin.user_manage")

    old_member = make_member(db_session, psn="LINK-007", email="link7@example.com")
    new_member = make_member(db_session, psn="LINK-008", email="link8@example.com")
    target_admin = make_admin_user(db_session, username="link_target_7", member_id=old_member.id)

    res = client.patch(
        f"/api/admin/users/{target_admin.id}/member-link",
        json={"member_id": str(new_member.id), "reason": "Changed EXCO assignment"},
        headers=auth_headers(manager),
    )
    assert res.status_code == 200
    assert res.json()["member_id"] == str(new_member.id)

    # The old member must now be free to link to someone else -- confirms
    # the change actually released the old link, not just added a second one.
    other_admin = make_admin_user(db_session, username="link_target_7b")
    res2 = client.patch(
        f"/api/admin/users/{other_admin.id}/member-link",
        json={"member_id": str(old_member.id)},
        headers=auth_headers(manager),
    )
    assert res2.status_code == 200


# ---------------------------------------------------------------------------
# Admin Identity Governance remediation, Governance Objective 2
# (Section 12, items 1-5): self-link protection
# ---------------------------------------------------------------------------


def test_1_admin_cannot_link_themselves_to_their_own_member(client, db_session, seed_permissions):
    admin = make_admin_user(db_session, username="selflink_1")
    grant_permission(db_session, admin, "admin.user_manage")
    member = make_member(db_session, psn="SELFLINK-001", email="selflink1@example.com")

    res = client.patch(
        f"/api/admin/users/{admin.id}/member-link",
        json={"member_id": str(member.id)},
        headers=auth_headers(admin),
    )
    assert res.status_code == 409
    assert res.json()["detail"]["error"] == "self_conflict"

    db_session.refresh(admin)
    assert admin.member_id is None, "the blocked attempt must not have partially applied"


def test_1b_super_admin_cannot_bypass_self_link_protection(client, db_session, seed_permissions):
    """Same as test 1, but for a super-admin -- confirms is_super_admin
    is never checked in this guard, consistent with self_conflict.py's
    established precedent elsewhere in this codebase."""
    admin = make_admin_user(db_session, username="selflink_1b", super_admin=True)
    member = make_member(db_session, psn="SELFLINK-001B", email="selflink1b@example.com")

    res = client.patch(
        f"/api/admin/users/{admin.id}/member-link",
        json={"member_id": str(member.id)},
        headers=auth_headers(admin),
    )
    assert res.status_code == 409
    assert res.json()["detail"]["error"] == "self_conflict"


def test_2_admin_links_another_admin_to_a_valid_member_succeeds(client, db_session, seed_permissions):
    manager = make_admin_user(db_session, username="selflink_2_manager")
    grant_permission(db_session, manager, "admin.user_manage")
    target = make_admin_user(db_session, username="selflink_2_target")
    member = make_member(db_session, psn="SELFLINK-002", email="selflink2@example.com")

    res = client.patch(
        f"/api/admin/users/{target.id}/member-link",
        json={"member_id": str(member.id)},
        headers=auth_headers(manager),
    )
    assert res.status_code == 200


def test_3_admin_cannot_link_themselves_to_a_different_member_either(client, db_session, seed_permissions):
    """Section 12 test 3 was deliberately ambiguous in the remediation
    prompt ('do not assume this is prohibited merely because self-link
    to their own Member is prohibited'). DECISION (documented here and in
    admin_users.py): a blanket rule was chosen -- an admin can never use
    this endpoint to link THEMSELVES to ANY member, not only 'their own'
    -- because allowing self-linking to a different member would still
    let an admin grant themselves control over their own identity
    mapping. This test pins that decision down; if a narrower rule was
    actually intended, this is the test (and the corresponding code in
    admin_users.py) to revisit."""
    admin = make_admin_user(db_session, username="selflink_3")
    grant_permission(db_session, admin, "admin.user_manage")
    # Deliberately a member with NO prior relationship to this admin at all.
    unrelated_member = make_member(db_session, psn="SELFLINK-003", email="selflink3@example.com")

    res = client.patch(
        f"/api/admin/users/{admin.id}/member-link",
        json={"member_id": str(unrelated_member.id)},
        headers=auth_headers(admin),
    )
    assert res.status_code == 409
    assert res.json()["detail"]["error"] == "self_conflict"


def test_4_changing_an_existing_link_continues_to_work(client, db_session, seed_permissions):
    """Same guarantee as test_changing_an_existing_link_to_a_different_member_succeeds
    above, restated per the remediation prompt's own numbering (Section
    12, item 4) for direct traceability."""
    manager = make_admin_user(db_session, username="selflink_4_manager")
    grant_permission(db_session, manager, "admin.user_manage")
    old_member = make_member(db_session, psn="SELFLINK-004A", email="selflink4a@example.com")
    new_member = make_member(db_session, psn="SELFLINK-004B", email="selflink4b@example.com")
    target = make_admin_user(db_session, username="selflink_4_target", member_id=old_member.id)

    res = client.patch(
        f"/api/admin/users/{target.id}/member-link",
        json={"member_id": str(new_member.id)},
        headers=auth_headers(manager),
    )
    assert res.status_code == 200
    assert res.json()["member_id"] == str(new_member.id)


def test_5_unlinking_a_valid_account_continues_to_work(client, db_session, seed_permissions):
    """Item 5: unlink continues to work 'unless blocked by the new role
    requirement' -- this case has no member-required role active, so it
    must succeed. The role-requirement-blocks-unlink case is covered
    separately in test_role_member_link_requirement.py."""
    manager = make_admin_user(db_session, username="selflink_5_manager")
    grant_permission(db_session, manager, "admin.user_manage")
    member = make_member(db_session, psn="SELFLINK-005", email="selflink5@example.com")
    target = make_admin_user(db_session, username="selflink_5_target", member_id=member.id)

    res = client.patch(
        f"/api/admin/users/{target.id}/member-link",
        json={"member_id": None},
        headers=auth_headers(manager),
    )
    assert res.status_code == 200
    assert res.json()["member_id"] is None


def test_5b_admin_can_unlink_their_own_account(client, db_session, seed_permissions):
    """Confirms the self-link blanket rule (tests 1/1b/3 above) applies
    only to ESTABLISHING/changing a link, not to removing one -- an admin
    removing their own link is explicitly allowed (see admin_users.py's
    comment on this exact point)."""
    admin = make_admin_user(db_session, username="selflink_5b")
    grant_permission(db_session, admin, "admin.user_manage")
    member = make_member(db_session, psn="SELFLINK-005B", email="selflink5b@example.com")
    admin.member_id = member.id
    db_session.commit()

    res = client.patch(
        f"/api/admin/users/{admin.id}/member-link",
        json={"member_id": None},
        headers=auth_headers(admin),
    )
    assert res.status_code == 200
    assert res.json()["member_id"] is None


def test_self_link_denial_is_audited(client, db_session, seed_permissions):
    from app import models

    admin = make_admin_user(db_session, username="selflink_audit")
    grant_permission(db_session, admin, "admin.user_manage")
    member = make_member(db_session, psn="SELFLINK-AUDIT", email="selflinkaudit@example.com")

    res = client.patch(
        f"/api/admin/users/{admin.id}/member-link",
        json={"member_id": str(member.id)},
        headers=auth_headers(admin),
    )
    assert res.status_code == 409

    event = (
        db_session.query(models.AuditEvent)
        .filter(models.AuditEvent.event_type == "admin.member_link_self_conflict_denied")
        .order_by(models.AuditEvent.created_at.desc())
        .first()
    )
    assert event is not None
    assert event.actor_user_id == admin.id
    assert event.entity_id == str(admin.id)

    # No false successful-linkage event must exist for this attempt.
    success_events = (
        db_session.query(models.AuditEvent)
        .filter(
            models.AuditEvent.event_type == "admin.user_member_link_changed",
            models.AuditEvent.entity_id == str(admin.id),
        )
        .count()
    )
    assert success_events == 0
