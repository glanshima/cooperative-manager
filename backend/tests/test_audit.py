from tests.conftest import auth_headers, grant_permission, make_admin_user, make_member


def test_failed_login_creates_audit_event(client, db_session):
    from app import models

    make_admin_user(db_session, username="audit_fail_admin", password="Passw0rd!")
    client.post("/api/auth/login", json={"username": "audit_fail_admin", "password": "wrong"})

    event = (
        db_session.query(models.AuditEvent)
        .filter(models.AuditEvent.event_type == "auth.login_failed")
        .filter(models.AuditEvent.actor_username == "audit_fail_admin")
        .first()
    )
    assert event is not None
    assert event.action == "login"


def test_successful_login_creates_audit_event_with_no_password_field(client, db_session):
    from app import models

    make_admin_user(db_session, username="audit_ok_admin", password="Passw0rd!")
    client.post("/api/auth/login", json={"username": "audit_ok_admin", "password": "Passw0rd!"})

    event = (
        db_session.query(models.AuditEvent)
        .filter(models.AuditEvent.event_type == "auth.login_succeeded")
        .first()
    )
    assert event is not None
    # Passwords must never appear in audit events (Section 6).
    assert event.new_values is None or "password" not in str(event.new_values).lower()


def test_member_update_creates_audit_event_with_actor_and_diff(client, db_session, seed_permissions):
    from app import models

    admin = make_admin_user(db_session, username="audit_member_admin")
    grant_permission(db_session, admin, "member.view", "member.update")
    member = make_member(db_session, psn="AUDIT-1", email="audit1@example.com")

    res = client.put(
        f"/api/members/{member.id}",
        json={"phone": "+2348012345678"},
        headers=auth_headers(admin),
    )
    assert res.status_code == 200

    event = (
        db_session.query(models.AuditEvent)
        .filter(models.AuditEvent.event_type == "member.updated")
        .filter(models.AuditEvent.entity_id == str(member.id))
        .first()
    )
    assert event is not None
    assert event.actor_username == "audit_member_admin"
    assert event.new_values.get("phone") == "+2348012345678"


def test_audit_log_not_reachable_without_audit_view_permission(client, db_session, seed_permissions):
    admin = make_admin_user(db_session, username="no_audit_perm_admin")
    res = client.get("/api/audit", headers=auth_headers(admin))
    assert res.status_code == 403


def test_audit_log_reachable_with_permission(client, db_session, seed_permissions):
    admin = make_admin_user(db_session, username="has_audit_perm_admin")
    grant_permission(db_session, admin, "audit.view")
    res = client.get("/api/audit", headers=auth_headers(admin))
    assert res.status_code == 200
