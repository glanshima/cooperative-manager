"""
Module-toggle enforcement (Settings.*_module_enabled).

The settings toggles previously did nothing; these tests pin the contract
that a disabled business module returns a clear 403 from its API routes
while auth, administration and settings remain reachable so it can be
re-enabled.
"""
from tests.conftest import auth_headers, make_admin_user, make_member, make_member_user

from app import models

LOAN_ROUTES = [
    "/api/loans",
    "/api/loan-types",
    "/api/loan-applications",
    "/api/loan-repayments",
]


def _set_modules(db_session, **overrides):
    settings = db_session.query(models.Settings).first()
    if settings is None:
        settings = models.Settings(**overrides)
        db_session.add(settings)
    else:
        for field, value in overrides.items():
            setattr(settings, field, value)
    db_session.commit()
    return settings


def test_modules_are_enabled_when_no_settings_row_exists(client, db_session):
    """A fresh install has no Settings row yet; the dependency must treat
    that as the model defaults (all modules enabled), not as disabled."""
    admin = make_admin_user(db_session, username="fresh_admin", super_admin=True)

    res = client.get("/api/loan-types", headers=auth_headers(admin))

    assert res.status_code == 200


def test_disabled_loans_blocks_every_loan_router(client, db_session):
    _set_modules(db_session, loans_module_enabled=False)
    admin = make_admin_user(db_session, username="loans_off_admin", super_admin=True)

    for path in LOAN_ROUTES:
        res = client.get(path, headers=auth_headers(admin))
        assert res.status_code == 403, path
        assert res.json()["detail"] == "The Loans module is disabled by an administrator.", path


def test_settings_and_admin_stay_reachable_when_loans_are_disabled(client, db_session):
    _set_modules(db_session, loans_module_enabled=False)
    admin = make_admin_user(db_session, username="loans_off_recover_admin", super_admin=True)

    assert client.get("/api/settings", headers=auth_headers(admin)).status_code == 200
    assert client.get("/api/admin/users", headers=auth_headers(admin)).status_code == 200

    res = client.put(
        "/api/settings",
        headers=auth_headers(admin),
        json={"loans_module_enabled": True},
    )
    assert res.status_code == 200

    assert client.get("/api/loan-types", headers=auth_headers(admin)).status_code == 200


def test_disabled_members_blocks_management_but_not_self_service(client, db_session):
    member = make_member(db_session, psn="PSN-MOD", email="mod@example.com")
    member_user = make_member_user(db_session, member)
    _set_modules(db_session, members_module_enabled=False)
    admin = make_admin_user(db_session, username="members_off_admin", super_admin=True)

    for path in ["/api/members", "/api/members/filter-options"]:
        res = client.get(path, headers=auth_headers(admin))
        assert res.status_code == 403, path
        assert res.json()["detail"] == "The Members module is disabled by an administrator.", path

    # Self-service dashboard data is not the Members management surface.
    res = client.get("/api/members/me", headers=auth_headers(member_user))
    assert res.status_code == 200
    assert res.json()["psn"] == "PSN-MOD"

    # User administration can still re-enable the module.
    assert client.get("/api/admin/users", headers=auth_headers(admin)).status_code == 200
