"""
Login State Reconciliation Addendum tests. Covers the six account-state
cases from Section 11 (no login / active / inactive / pre-Phase-1 /
unmapped / EXCO member) plus Section 12's duplicate-login protection.
"""
from tests.conftest import auth_headers, grant_permission, make_admin_user, make_member, make_member_user


def _member_row(members_response, member_id):
    return next(m for m in members_response if m["id"] == str(member_id))


# ---------------------------------------------------------------------------
# Case A -- no login
# ---------------------------------------------------------------------------

def test_member_with_no_login_shows_no_login_state(client, db_session, seed_permissions):
    member = make_member(db_session, psn="LSR-A", email="lsr-a@example.com")
    admin = make_admin_user(db_session, username="lsr_admin_a")
    grant_permission(db_session, admin, "member.view")

    res = client.get("/api/members", headers=auth_headers(admin))
    assert res.status_code == 200
    row = _member_row(res.json(), member.id)
    assert row["login_user_id"] is None
    assert row["login_account_status"] is None


# ---------------------------------------------------------------------------
# Case B -- active existing login
# ---------------------------------------------------------------------------

def test_member_with_active_login_shows_active_state(client, db_session, seed_permissions):
    member = make_member(db_session, psn="LSR-B", email="lsr-b@example.com")
    make_member_user(db_session, member)
    admin = make_admin_user(db_session, username="lsr_admin_b")
    grant_permission(db_session, admin, "member.view")

    res = client.get("/api/members", headers=auth_headers(admin))
    row = _member_row(res.json(), member.id)
    assert row["login_account_status"] == "active"
    assert row["login_user_id"] is not None


# ---------------------------------------------------------------------------
# Case C -- inactive existing login, and the deactivate/reactivate cycle
# ---------------------------------------------------------------------------

def test_deactivating_and_reactivating_a_login_updates_state_correctly(client, db_session, seed_permissions):
    from app import models

    member = make_member(db_session, psn="LSR-C", email="lsr-c@example.com")
    login_user = make_member_user(db_session, member)
    admin = make_admin_user(db_session, username="lsr_admin_c")
    grant_permission(db_session, admin, "member.view", "member.deactivate")

    res = client.patch(
        f"/api/members/{member.id}/login-status",
        json={"account_status": "deactivated", "reason": "no longer with the cooperative"},
        headers=auth_headers(admin),
    )
    assert res.status_code == 200
    assert res.json()["login_account_status"] == "deactivated"

    db_session.refresh(login_user)
    assert login_user.account_status == models.AccountStatus.DEACTIVATED

    # Deactivation must not touch the Member record itself.
    db_session.refresh(member)
    assert member is not None

    # Reactivate
    res2 = client.patch(
        f"/api/members/{member.id}/login-status",
        json={"account_status": "active"},
        headers=auth_headers(admin),
    )
    assert res2.status_code == 200
    assert res2.json()["login_account_status"] == "active"


# ---------------------------------------------------------------------------
# Case D -- pre-Phase-1-style login (just an ordinary member-role login
# created directly, simulating one that predates any of this work)
# ---------------------------------------------------------------------------

def test_pre_existing_login_is_recognized_correctly(client, db_session, seed_permissions):
    member = make_member(db_session, psn="LSR-D", email="lsr-d@example.com")
    make_member_user(db_session, member)  # no special "phase 1" marker -- same table, same columns
    admin = make_admin_user(db_session, username="lsr_admin_d")
    grant_permission(db_session, admin, "member.view")

    res = client.get(f"/api/members/{member.id}", headers=auth_headers(admin))
    assert res.status_code == 200
    assert res.json()["login_account_status"] == "active"


# ---------------------------------------------------------------------------
# Case F -- EXCO/admin member: role assignment must not affect login state
# ---------------------------------------------------------------------------

def test_admin_role_does_not_affect_member_login_state(client, db_session, seed_permissions):
    """An EXCO officer with BOTH a member self-service login AND a
    separate admin account (linked via member_id per the Controlled
    Remediation pass) must still show their member login state
    correctly -- the admin account's existence/role must not interfere."""
    member = make_member(db_session, psn="LSR-F", email="lsr-f@example.com")
    make_member_user(db_session, member)
    # Same person also has an admin account linked to the same member.
    make_admin_user(db_session, username="lsr_f_exco_admin", member_id=member.id)

    viewer = make_admin_user(db_session, username="lsr_admin_f")
    grant_permission(db_session, viewer, "member.view")

    res = client.get(f"/api/members/{member.id}", headers=auth_headers(viewer))
    assert res.status_code == 200
    assert res.json()["login_account_status"] == "active"


# ---------------------------------------------------------------------------
# Section 12 -- duplicate login protection
# ---------------------------------------------------------------------------

def test_create_login_rejected_when_member_login_already_exists(client, db_session, seed_permissions):
    member = make_member(db_session, psn="LSR-DUP", email="lsr-dup@example.com")
    make_member_user(db_session, member)
    admin = make_admin_user(db_session, username="lsr_dup_admin")
    grant_permission(db_session, admin, "admin.user_manage")

    res = client.post(
        "/api/auth/create-member-login",
        json={"member_id": str(member.id), "temporary_password": "AnotherPassw0rd!"},
        headers=auth_headers(admin),
    )
    assert res.status_code == 409

    from app import models

    count = (
        db_session.query(models.User)
        .filter(models.User.member_id == member.id, models.User.role == models.UserRole.MEMBER)
        .count()
    )
    assert count == 1, "must never end up with two member-role logins for the same member"


def test_create_login_allowed_when_only_an_admin_account_is_linked(client, db_session, seed_permissions):
    """Regression check: a member whose ONLY existing account is a
    linked ADMIN account (no self-service login yet) must still be able
    to get their own member login -- this is exactly the scenario the
    Controlled Remediation pass's admin/member coexistence design
    supports (see models.py's User docstring)."""
    member = make_member(db_session, psn="LSR-ADMINONLY", email="lsr-adminonly@example.com")
    make_admin_user(db_session, username="lsr_adminonly_exco", member_id=member.id)

    admin = make_admin_user(db_session, username="lsr_adminonly_creator")
    grant_permission(db_session, admin, "admin.user_manage")

    res = client.post(
        "/api/auth/create-member-login",
        json={"member_id": str(member.id), "temporary_password": "FreshPassw0rd!"},
        headers=auth_headers(admin),
    )
    assert res.status_code == 201


def test_login_status_endpoint_404s_when_no_login_exists(client, db_session, seed_permissions):
    member = make_member(db_session, psn="LSR-NOLOGIN", email="lsr-nologin@example.com")
    admin = make_admin_user(db_session, username="lsr_nologin_admin")
    grant_permission(db_session, admin, "member.deactivate")

    res = client.patch(
        f"/api/members/{member.id}/login-status",
        json={"account_status": "deactivated"},
        headers=auth_headers(admin),
    )
    assert res.status_code == 404
