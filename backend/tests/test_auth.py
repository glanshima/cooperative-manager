from tests.conftest import (
    auth_headers,
    grant_permission,
    make_admin_user,
    make_member,
    make_member_user,
)
from app import models


def test_valid_login_succeeds(client, db_session):
    admin = make_admin_user(db_session, username="admin_ok", password="Passw0rd!")
    res = client.post("/api/auth/login", json={"username": "admin_ok", "password": "Passw0rd!"})
    assert res.status_code == 200
    body = res.json()
    assert "access_token" in body
    assert body["role"] == "admin"


def test_invalid_password_rejected(client, db_session):
    make_admin_user(db_session, username="admin_bad", password="Passw0rd!")
    res = client.post("/api/auth/login", json={"username": "admin_bad", "password": "wrong"})
    assert res.status_code == 401


def test_unknown_username_rejected_without_leaking_existence(client, db_session):
    res = client.post("/api/auth/login", json={"username": "nobody-here", "password": "whatever"})
    assert res.status_code == 401


def test_brute_force_lockout(client, db_session):
    admin = make_admin_user(db_session, username="admin_lock", password="Passw0rd!")
    for _ in range(5):
        res = client.post("/api/auth/login", json={"username": "admin_lock", "password": "wrong"})
        assert res.status_code == 401

    # 6th attempt, even with the CORRECT password, must be locked out.
    res = client.post("/api/auth/login", json={"username": "admin_lock", "password": "Passw0rd!"})
    assert res.status_code == 423


def test_deactivated_account_cannot_login(client, db_session):
    admin = make_admin_user(db_session, username="admin_deact", password="Passw0rd!")
    admin.account_status = models.AccountStatus.DEACTIVATED
    admin.is_active = False
    db_session.commit()

    res = client.post("/api/auth/login", json={"username": "admin_deact", "password": "Passw0rd!"})
    assert res.status_code == 401


def test_deactivated_admin_loses_access_immediately_on_existing_token(client, db_session):
    """An admin's already-issued token must stop working the moment their
    account is deactivated -- not just at their next login attempt."""
    admin = make_admin_user(db_session, username="admin_immediate", password="Passw0rd!", super_admin=True)
    login = client.post(
        "/api/auth/login", json={"username": "admin_immediate", "password": "Passw0rd!"}
    )
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Works while active.
    res = client.get("/api/auth/me", headers=headers)
    assert res.status_code == 200

    admin.account_status = models.AccountStatus.DEACTIVATED
    admin.is_active = False
    db_session.commit()

    res = client.get("/api/auth/me", headers=headers)
    assert res.status_code == 401


def test_password_policy_rejects_weak_password(client, db_session):
    member = make_member(db_session)
    admin = make_admin_user(db_session, username="admin_policy", password="Passw0rd!", super_admin=True)
    login = client.post("/api/auth/login", json={"username": "admin_policy", "password": "Passw0rd!"})
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    res = client.post(
        "/api/auth/create-member-login",
        json={"member_id": str(member.id), "temporary_password": "short"},
        headers=headers,
    )
    assert res.status_code == 400


def test_logout_revokes_session(client, db_session):
    admin = make_admin_user(db_session, username="admin_logout", password="Passw0rd!")
    login = client.post("/api/auth/login", json={"username": "admin_logout", "password": "Passw0rd!"})
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    assert client.get("/api/auth/me", headers=headers).status_code == 200
    assert client.post("/api/auth/logout", headers=headers).status_code == 204
    # The same token must no longer work after logout.
    assert client.get("/api/auth/me", headers=headers).status_code == 401


def test_me_reports_the_members_stored_name(client, db_session):
    member = make_member(db_session, psn="PSN-ME-1", name="Ada Obi")
    make_member_user(db_session, member)

    login = client.post("/api/auth/login", json={"username": "PSN-ME-1", "password": "Passw0rd!"})
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    body = client.get("/api/auth/me", headers=headers).json()
    # The stored name is returned whole; the dashboard derives "Last, First".
    assert body["member_name"] == "Ada Obi"


def test_me_only_names_an_admin_through_a_linked_member(client, db_session):
    member = make_member(db_session, psn="PSN-ME-2", name="Bola Ade")
    unlinked = make_admin_user(db_session, username="admin_unlinked", password="Passw0rd!")
    make_admin_user(
        db_session,
        username="admin_linked",
        password="Passw0rd!",
        member_id=member.id,
    )

    def me(username):
        login = client.post("/api/auth/login", json={"username": username, "password": "Passw0rd!"})
        headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
        return client.get("/api/auth/me", headers=headers).json()

    assert unlinked.member_id is None
    assert me("admin_unlinked")["member_name"] is None
    assert me("admin_linked")["member_name"] == "Bola Ade"


def test_me_reports_only_the_permissions_the_account_holds(client, db_session, seed_permissions):
    admin = make_admin_user(db_session, username="admin_me_scoped")
    grant_permission(db_session, admin, "member.view", "loan.view")

    body = client.get("/api/auth/me", headers=auth_headers(admin)).json()

    assert body["permissions"] == ["loan.view", "member.view"]


def test_me_reports_the_whole_catalogue_for_a_super_admin(client, db_session, seed_permissions):
    from app.permissions_catalogue import PERMISSION_CODES

    admin = make_admin_user(db_session, username="admin_me_super", super_admin=True)

    body = client.get("/api/auth/me", headers=auth_headers(admin)).json()

    assert body["permissions"] == sorted(PERMISSION_CODES)
    assert "branding.manage" in body["permissions"]


def test_me_reports_no_permissions_for_a_member(client, db_session):
    member = make_member(db_session, psn="PSN-ME-PERMS", name="Ada Obi")
    member_user = make_member_user(db_session, member)

    body = client.get("/api/auth/me", headers=auth_headers(member_user)).json()

    assert body["permissions"] == []


def test_create_member_login_requires_member_update_permission(client, db_session, seed_permissions):
    member = make_member(db_session, psn="PSN-CREATE-NOPERM", email="create-noperm@example.com")
    admin = make_admin_user(db_session, username="admin_create_noperm")
    grant_permission(db_session, admin, "admin.user_manage")

    res = client.post(
        "/api/auth/create-member-login",
        json={"member_id": str(member.id), "temporary_password": "ValidPassw0rd!"},
        headers=auth_headers(admin),
    )

    assert res.status_code == 403
