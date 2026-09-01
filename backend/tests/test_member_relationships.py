"""Tests for the Member Relationship / Next-of-Kin Controlled
Remediation (2026-09): POST/PUT /api/members' next_of_kin_is_member /
next_of_kin_member_id handling, member_relationships.py's
set_relationship/clear_relationship/has_member_conflict, the
self-reference guard, and the at-most-one-active-per-type constraint.

STANDING NOTE (same as every other test file in this suite): these are
WRITTEN BUT NOT YET EXECUTED against a real database -- verified only
via `python -m py_compile` and manual tracing. conftest.py requires a
real Postgres DATABASE_URL (see its module docstring) and this sandbox
has neither network access nor a reachable Postgres instance. Running
this suite for real against a disposable Postgres database remains the
single highest-value next action for this engagement.
"""
from tests.conftest import auth_headers, grant_permission, make_admin_user, make_member


def test_create_member_requires_next_of_kin_is_member_field(client, db_session, seed_permissions):
    """Member Relationship remediation, Section 1: the field is
    required with no default -- omitting it entirely is a 422, not a
    silent pass."""
    admin = make_admin_user(db_session, username="nok_create_admin_1")
    grant_permission(db_session, admin, "member.create")

    res = client.post(
        "/api/members",
        json={"psn": "NOK-001", "name": "Member One"},
        headers=auth_headers(admin),
    )
    assert res.status_code == 422


def test_create_member_with_manual_next_of_kin(client, db_session, seed_permissions):
    admin = make_admin_user(db_session, username="nok_create_admin_2")
    grant_permission(db_session, admin, "member.create")

    res = client.post(
        "/api/members",
        json={
            "psn": "NOK-002",
            "name": "Member Two",
            "next_of_kin_is_member": False,
            "next_of_kin": "Jane Doe",
            "next_of_kin_phone": "+2348012345678",
        },
        headers=auth_headers(admin),
    )
    assert res.status_code == 201
    body = res.json()
    assert body["next_of_kin_is_member"] is False
    assert body["next_of_kin_member"] is None
    assert body["next_of_kin"] == "Jane Doe"


def test_create_member_with_member_next_of_kin(client, db_session, seed_permissions):
    from app import models

    admin = make_admin_user(db_session, username="nok_create_admin_3")
    grant_permission(db_session, admin, "member.create")

    nok_member = make_member(db_session, psn="NOK-KIN-001", email="kin1@example.com")

    res = client.post(
        "/api/members",
        json={
            "psn": "NOK-003",
            "name": "Member Three",
            "next_of_kin_is_member": True,
            "next_of_kin_member_id": str(nok_member.id),
        },
        headers=auth_headers(admin),
    )
    assert res.status_code == 201
    body = res.json()
    assert body["next_of_kin_is_member"] is True
    assert body["next_of_kin_member"]["id"] == str(nok_member.id)
    assert body["next_of_kin_member"]["psn"] == "NOK-KIN-001"

    relationship = (
        db_session.query(models.MemberRelationship)
        .filter(models.MemberRelationship.member_id == body["id"])
        .first()
    )
    assert relationship is not None
    assert str(relationship.related_member_id) == str(nok_member.id)
    assert relationship.status == models.RelationshipStatus.ACTIVE
    assert relationship.conflict_of_interest is True


def test_create_member_next_of_kin_member_id_required_when_true(client, db_session, seed_permissions):
    admin = make_admin_user(db_session, username="nok_create_admin_4")
    grant_permission(db_session, admin, "member.create")

    res = client.post(
        "/api/members",
        json={"psn": "NOK-004", "name": "Member Four", "next_of_kin_is_member": True},
        headers=auth_headers(admin),
    )
    assert res.status_code == 422


def test_create_member_next_of_kin_member_id_forbidden_when_false(client, db_session, seed_permissions):
    admin = make_admin_user(db_session, username="nok_create_admin_5")
    grant_permission(db_session, admin, "member.create")

    other = make_member(db_session, psn="NOK-KIN-002", email="kin2@example.com")
    res = client.post(
        "/api/members",
        json={
            "psn": "NOK-005",
            "name": "Member Five",
            "next_of_kin_is_member": False,
            "next_of_kin_member_id": str(other.id),
        },
        headers=auth_headers(admin),
    )
    assert res.status_code == 422


def test_next_of_kin_member_must_exist(client, db_session, seed_permissions):
    admin = make_admin_user(db_session, username="nok_create_admin_6")
    grant_permission(db_session, admin, "member.create")

    res = client.post(
        "/api/members",
        json={
            "psn": "NOK-006",
            "name": "Member Six",
            "next_of_kin_is_member": True,
            "next_of_kin_member_id": "00000000-0000-0000-0000-000000000000",
        },
        headers=auth_headers(admin),
    )
    assert res.status_code == 404


def test_update_member_can_change_next_of_kin_to_a_different_member(client, db_session, seed_permissions):
    from app import models

    admin = make_admin_user(db_session, username="nok_update_admin_1")
    grant_permission(db_session, admin, "member.create")
    grant_permission(db_session, admin, "member.update")

    kin_a = make_member(db_session, psn="NOK-KIN-A", email="kina@example.com")
    kin_b = make_member(db_session, psn="NOK-KIN-B", email="kinb@example.com")

    create_res = client.post(
        "/api/members",
        json={
            "psn": "NOK-010",
            "name": "Member Ten",
            "next_of_kin_is_member": True,
            "next_of_kin_member_id": str(kin_a.id),
        },
        headers=auth_headers(admin),
    )
    member_id = create_res.json()["id"]

    update_res = client.put(
        f"/api/members/{member_id}",
        json={"next_of_kin_is_member": True, "next_of_kin_member_id": str(kin_b.id)},
        headers=auth_headers(admin),
    )
    assert update_res.status_code == 200
    assert update_res.json()["next_of_kin_member"]["id"] == str(kin_b.id)

    # Old relationship row is preserved, marked removed -- never deleted
    # (Section 8/17: audit history retains who the previous Next of Kin
    # was).
    rows = (
        db_session.query(models.MemberRelationship)
        .filter(models.MemberRelationship.member_id == member_id)
        .order_by(models.MemberRelationship.created_at)
        .all()
    )
    assert len(rows) == 2
    assert rows[0].status == models.RelationshipStatus.REMOVED
    assert str(rows[0].related_member_id) == str(kin_a.id)
    assert rows[1].status == models.RelationshipStatus.ACTIVE
    assert str(rows[1].related_member_id) == str(kin_b.id)


def test_update_member_can_clear_member_next_of_kin_back_to_manual(client, db_session, seed_permissions):
    from app import models

    admin = make_admin_user(db_session, username="nok_update_admin_2")
    grant_permission(db_session, admin, "member.create")
    grant_permission(db_session, admin, "member.update")

    kin = make_member(db_session, psn="NOK-KIN-C", email="kinc@example.com")

    create_res = client.post(
        "/api/members",
        json={
            "psn": "NOK-011",
            "name": "Member Eleven",
            "next_of_kin_is_member": True,
            "next_of_kin_member_id": str(kin.id),
        },
        headers=auth_headers(admin),
    )
    member_id = create_res.json()["id"]

    update_res = client.put(
        f"/api/members/{member_id}",
        json={
            "next_of_kin_is_member": False,
            "next_of_kin": "Manual Kin Name",
            "next_of_kin_phone": "+2348099998888",
        },
        headers=auth_headers(admin),
    )
    assert update_res.status_code == 200
    body = update_res.json()
    assert body["next_of_kin_is_member"] is False
    assert body["next_of_kin_member"] is None
    assert body["next_of_kin"] == "Manual Kin Name"

    relationship = (
        db_session.query(models.MemberRelationship)
        .filter(models.MemberRelationship.member_id == member_id)
        .first()
    )
    assert relationship.status == models.RelationshipStatus.REMOVED


def test_update_member_without_next_of_kin_field_leaves_relationship_untouched(
    client, db_session, seed_permissions
):
    """Section 8: omitting next_of_kin_is_member entirely from an
    ordinary edit must not touch the existing relationship at all."""
    from app import models

    admin = make_admin_user(db_session, username="nok_update_admin_3")
    grant_permission(db_session, admin, "member.create")
    grant_permission(db_session, admin, "member.update")

    kin = make_member(db_session, psn="NOK-KIN-D", email="kind@example.com")
    create_res = client.post(
        "/api/members",
        json={
            "psn": "NOK-012",
            "name": "Member Twelve",
            "next_of_kin_is_member": True,
            "next_of_kin_member_id": str(kin.id),
        },
        headers=auth_headers(admin),
    )
    member_id = create_res.json()["id"]

    update_res = client.put(
        f"/api/members/{member_id}",
        json={"phone": "+2348011112222"},
        headers=auth_headers(admin),
    )
    assert update_res.status_code == 200
    assert update_res.json()["next_of_kin_is_member"] is True
    assert update_res.json()["next_of_kin_member"]["id"] == str(kin.id)

    relationship = (
        db_session.query(models.MemberRelationship)
        .filter(models.MemberRelationship.member_id == member_id)
        .first()
    )
    assert relationship.status == models.RelationshipStatus.ACTIVE


def test_member_cannot_be_own_next_of_kin(client, db_session, seed_permissions):
    admin = make_admin_user(db_session, username="nok_self_admin")
    grant_permission(db_session, admin, "member.create")
    grant_permission(db_session, admin, "member.update")

    member = make_member(db_session, psn="NOK-020", email="self1@example.com")

    res = client.put(
        f"/api/members/{member.id}",
        json={"next_of_kin_is_member": True, "next_of_kin_member_id": str(member.id)},
        headers=auth_headers(admin),
    )
    assert res.status_code == 409
    assert res.json()["detail"]["error"] == "self_reference"


def test_setting_same_next_of_kin_again_is_a_no_op(client, db_session, seed_permissions):
    """Re-sending the same related member shouldn't remove+recreate the
    row (and shouldn't emit a pointless second audit event)."""
    from app import models

    admin = make_admin_user(db_session, username="nok_noop_admin")
    grant_permission(db_session, admin, "member.create")
    grant_permission(db_session, admin, "member.update")

    kin = make_member(db_session, psn="NOK-KIN-E", email="kine@example.com")
    create_res = client.post(
        "/api/members",
        json={
            "psn": "NOK-021",
            "name": "Member Twenty-One",
            "next_of_kin_is_member": True,
            "next_of_kin_member_id": str(kin.id),
        },
        headers=auth_headers(admin),
    )
    member_id = create_res.json()["id"]

    update_res = client.put(
        f"/api/members/{member_id}",
        json={"next_of_kin_is_member": True, "next_of_kin_member_id": str(kin.id)},
        headers=auth_headers(admin),
    )
    assert update_res.status_code == 200

    rows = (
        db_session.query(models.MemberRelationship)
        .filter(models.MemberRelationship.member_id == member_id)
        .all()
    )
    assert len(rows) == 1
    assert rows[0].status == models.RelationshipStatus.ACTIVE


def test_at_most_one_active_next_of_kin_enforced_at_db_level(db_session, seed_permissions):
    """Direct-DB test of the partial unique index -- a second ACTIVE
    next_of_kin row for the same member_id must be rejected even
    bypassing the application layer entirely."""
    from sqlalchemy.exc import IntegrityError

    from app import models

    member = make_member(db_session, psn="NOK-030", email="dup1@example.com")
    kin_a = make_member(db_session, psn="NOK-KIN-F", email="kinf@example.com")
    kin_b = make_member(db_session, psn="NOK-KIN-G", email="king@example.com")

    db_session.add(
        models.MemberRelationship(member_id=member.id, related_member_id=kin_a.id)
    )
    db_session.commit()

    db_session.add(
        models.MemberRelationship(member_id=member.id, related_member_id=kin_b.id)
    )
    try:
        db_session.commit()
        assert False, "Expected the partial unique index to reject a second active row"
    except IntegrityError:
        db_session.rollback()


def test_next_of_kin_requires_member_create_permission(client, db_session, seed_permissions):
    no_perm_admin = make_admin_user(db_session, username="nok_no_perm_admin")
    kin = make_member(db_session, psn="NOK-KIN-H", email="kinh@example.com")

    res = client.post(
        "/api/members",
        json={
            "psn": "NOK-040",
            "name": "Member Forty",
            "next_of_kin_is_member": True,
            "next_of_kin_member_id": str(kin.id),
        },
        headers=auth_headers(no_perm_admin),
    )
    assert res.status_code == 403


# ---------------------------------------------------------------------
# member_relationships.has_member_conflict -- governance foundation
# ---------------------------------------------------------------------


def test_has_member_conflict_true_in_both_directions(db_session, seed_permissions):
    from app import member_relationships, models

    member_a = make_member(db_session, psn="CONF-001", email="confa@example.com")
    member_b = make_member(db_session, psn="CONF-002", email="confb@example.com")
    db_session.add(models.MemberRelationship(member_id=member_a.id, related_member_id=member_b.id))
    db_session.commit()

    assert member_relationships.has_member_conflict(db_session, member_a.id, member_b.id) is True
    # Reverse direction from the single stored row must also resolve true.
    assert member_relationships.has_member_conflict(db_session, member_b.id, member_a.id) is True


def test_has_member_conflict_false_when_unrelated(db_session, seed_permissions):
    from app import member_relationships

    member_a = make_member(db_session, psn="CONF-003", email="confc@example.com")
    member_b = make_member(db_session, psn="CONF-004", email="confd@example.com")

    assert member_relationships.has_member_conflict(db_session, member_a.id, member_b.id) is False


def test_has_member_conflict_false_after_relationship_removed(db_session, seed_permissions):
    from app import member_relationships, models

    admin = make_admin_user(db_session, username="conf_remove_admin")
    member_a = make_member(db_session, psn="CONF-005", email="confe@example.com")
    member_b = make_member(db_session, psn="CONF-006", email="conff@example.com")

    member_relationships.set_relationship(
        db_session, member=member_a, related_member_id=member_b.id, actor=admin
    )
    assert member_relationships.has_member_conflict(db_session, member_a.id, member_b.id) is True

    member_relationships.clear_relationship(db_session, member=member_a, actor=admin)
    assert member_relationships.has_member_conflict(db_session, member_a.id, member_b.id) is False


def test_has_member_conflict_false_for_identical_or_none_ids(db_session, seed_permissions):
    from app import member_relationships

    member_a = make_member(db_session, psn="CONF-007", email="confg@example.com")

    assert member_relationships.has_member_conflict(db_session, member_a.id, member_a.id) is False
    assert member_relationships.has_member_conflict(db_session, member_a.id, None) is False
    assert member_relationships.has_member_conflict(db_session, None, member_a.id) is False
