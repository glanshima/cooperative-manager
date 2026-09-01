"""
Test fixtures for the Phase 1 test suite.

REQUIRES a real Postgres database reachable via DATABASE_URL (e.g. a
disposable Neon branch or a local Postgres) -- the app's models use
Postgres-specific column types (UUID, JSONB-with-fallback), and Phase 1's
concurrency tests specifically exercise `SELECT ... FOR UPDATE` row
locking, which SQLite doesn't support in a way that's representative of
production. Point DATABASE_URL at a throwaway database, never at a real
cooperative's data -- this suite creates and truncates tables freely.

    export DATABASE_URL="postgresql://.../mact_test"
    export SECRET_KEY="test-only-secret"
    cd backend && pytest

Each test runs inside an outer transaction that is rolled back afterward
(the standard SQLAlchemy "join a SAVEPOINT" pattern), so tests don't
leak data into each other and don't require a fresh database per run.
"""
import os
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("SECRET_KEY", "test-only-secret-do-not-use-in-production")
os.environ.setdefault("DATABASE_URL", os.environ.get("DATABASE_URL", ""))

if not os.environ["DATABASE_URL"]:
    pytest.skip(
        "DATABASE_URL is not set -- point it at a disposable test Postgres database to run this suite",
        allow_module_level=True,
    )

from app import models  # noqa: E402
from app.database import Base, get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.auth import hash_password, create_access_token  # noqa: E402
from app.permissions_catalogue import PERMISSION_CATALOGUE  # noqa: E402

engine = create_engine(os.environ["DATABASE_URL"])
TestSessionLocal = sessionmaker(bind=engine)


@pytest.fixture(scope="session", autouse=True)
def _create_schema():
    Base.metadata.create_all(bind=engine)
    yield


@pytest.fixture()
def db_session():
    connection = engine.connect()
    trans = connection.begin()
    session = TestSessionLocal(bind=connection)

    # Support nested transactions (routers call db.commit() internally,
    # which would normally end our outer transaction) by restarting a
    # SAVEPOINT every time one closes.
    nested = connection.begin_nested()

    @event.listens_for(session, "after_transaction_end")
    def restart_savepoint(sess, trans_):
        nonlocal nested
        if not nested.is_active:
            nested = connection.begin_nested()

    yield session

    session.close()
    trans.rollback()
    connection.close()


@pytest.fixture()
def client(db_session):
    def _override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture()
def seed_permissions(db_session):
    """Seeds the permission catalogue only (not default roles) -- tests
    build their own minimal roles so each test's fixture setup is
    self-explanatory."""
    for code, category, description in PERMISSION_CATALOGUE:
        db_session.add(models.Permission(code=code, category=category, description=description))
    db_session.commit()


def make_member(db_session, psn="PSN-0001", name="Test Member", email="member@example.com", **extra):
    member = models.Member(
        psn=psn, name=name, email=email, status=extra.pop("status", models.MemberStatus.FINANCIAL), **extra
    )
    db_session.add(member)
    db_session.commit()
    db_session.refresh(member)
    return member


def make_member_user(db_session, member, password="Passw0rd!"):
    user = models.User(
        username=member.psn,
        password_hash=hash_password(password),
        role=models.UserRole.MEMBER,
        member_id=member.id,
        must_change_password=False,
        account_status=models.AccountStatus.ACTIVE,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def make_admin_user(db_session, username="admin1", password="Passw0rd!", super_admin=False, member_id=None):
    user = models.User(
        username=username,
        password_hash=hash_password(password),
        role=models.UserRole.ADMIN,
        must_change_password=False,
        account_status=models.AccountStatus.ACTIVE,
        is_super_admin=super_admin,
        member_id=member_id,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def grant_permission(db_session, user, *permission_codes, role_name=None, requires_member_link=False):
    role_name = role_name or f"role-{uuid.uuid4().hex[:8]}"
    role = models.Role(name=role_name, requires_member_link=requires_member_link)
    db_session.add(role)
    db_session.flush()
    for code in permission_codes:
        permission = db_session.query(models.Permission).filter(models.Permission.code == code).first()
        assert permission is not None, f"Permission {code!r} not seeded -- use the seed_permissions fixture"
        db_session.add(models.RolePermission(role_id=role.id, permission_id=permission.id))
    db_session.add(models.UserRoleAssignment(user_id=user.id, role_id=role.id))
    db_session.commit()
    return role


def make_role(db_session, name=None, requires_member_link=False, permission_codes=()):
    """Creates a Role WITHOUT assigning it to anyone -- for tests that
    need to call the actual assignment endpoint (POST .../assignments)
    themselves, rather than grant_permission's direct-DB auto-assignment."""
    role = models.Role(name=name or f"role-{uuid.uuid4().hex[:8]}", requires_member_link=requires_member_link)
    db_session.add(role)
    db_session.flush()
    for code in permission_codes:
        permission = db_session.query(models.Permission).filter(models.Permission.code == code).first()
        assert permission is not None, f"Permission {code!r} not seeded -- use the seed_permissions fixture"
        db_session.add(models.RolePermission(role_id=role.id, permission_id=permission.id))
    db_session.commit()
    db_session.refresh(role)
    return role


def auth_headers(user) -> dict:
    token, jti, expires_at = create_access_token(user_id=str(user.id), role=user.role.value)
    return {"Authorization": f"Bearer {token}"}
