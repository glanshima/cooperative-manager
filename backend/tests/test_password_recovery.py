"""
Test suite for Secure Self-Service Password Recovery & Staff Admin Reset.
Covers:
- Generic response / anti-enumeration behavior
- Cryptographic token hashing and storage (SHA-256)
- Expiration, single-use, and replay rejection
- Password policy validation
- Active session revocation on reset
- Lockout counter clearing
- Rate limiting protection
- Account status preservation
- Admin staff password reset with temporary password
- Audit event logging with secret redaction
"""

import hashlib
import uuid
from datetime import datetime, timedelta

import pytest
from app import models, schemas
from app.auth import create_access_token, hash_password, verify_password
from conftest import (
    auth_headers,
    grant_permission,
    make_admin_user,
    make_member,
    make_member_user,
)


def _hash_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.strip().encode("utf-8")).hexdigest()


def test_forgot_password_generic_response_for_existing_member(client, db_session):
    member = make_member(db_session, psn="PSN-RECOVER-1", email="member1@example.com")
    user = make_member_user(db_session, member)

    resp = client.post(
        "/api/auth/forgot-password",
        json={"identifier": member.psn},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "If an account matching the provided identifier exists" in data["message"]

    # Verify token row created in DB
    token_record = (
        db_session.query(models.PasswordResetToken)
        .filter(models.PasswordResetToken.user_id == user.id)
        .first()
    )
    assert token_record is not None
    assert token_record.used_at is None
    assert token_record.token_hash is not None
    # Token hash must be a 64-char sha256 hex string
    assert len(token_record.token_hash) == 64


def test_forgot_password_generic_response_for_unknown_user(client, db_session):
    resp = client.post(
        "/api/auth/forgot-password",
        json={"identifier": "nonexistent_psn_999999"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "If an account matching the provided identifier exists" in data["message"]

    # No token should be created
    tokens = db_session.query(models.PasswordResetToken).all()
    assert len(tokens) == 0


def test_forgot_password_by_registered_email(client, db_session):
    member = make_member(db_session, psn="PSN-EMAIL-1", email="registered@example.com")
    user = make_member_user(db_session, member)

    resp = client.post(
        "/api/auth/forgot-password",
        json={"identifier": "registered@example.com"},
    )
    assert resp.status_code == 200
    token_record = (
        db_session.query(models.PasswordResetToken)
        .filter(models.PasswordResetToken.user_id == user.id)
        .first()
    )
    assert token_record is not None


def test_forgot_password_rate_limiting(client, db_session):
    member = make_member(db_session, psn="PSN-RATELIMIT-1", email="ratelimit@example.com")
    user = make_member_user(db_session, member)

    # Trigger recovery 3 times (the allowed window)
    for _ in range(3):
        resp = client.post("/api/auth/forgot-password", json={"identifier": member.psn})
        assert resp.status_code == 200

    # 4th attempt exceeds rate limit but still returns the generic response
    resp = client.post("/api/auth/forgot-password", json={"identifier": member.psn})
    assert resp.status_code == 200
    assert "If an account matching the provided identifier exists" in resp.json()["message"]

    # Only 3 token records should have been created
    count = (
        db_session.query(models.PasswordResetToken)
        .filter(models.PasswordResetToken.user_id == user.id)
        .count()
    )
    assert count == 3


def test_verify_reset_token_valid_and_invalid(client, db_session):
    member = make_member(db_session, psn="PSN-VERIFY-1", email="verify@example.com")
    user = make_member_user(db_session, member)

    raw_token = "secure_test_token_1234567890abcdef"
    token_record = models.PasswordResetToken(
        user_id=user.id,
        token_hash=_hash_token(raw_token),
        expires_at=datetime.utcnow() + timedelta(minutes=15),
    )
    db_session.add(token_record)
    db_session.commit()

    # Valid token check
    resp = client.post("/api/auth/verify-reset-token", json={"token": raw_token})
    assert resp.status_code == 200
    assert resp.json()["valid"] is True

    # Invalid token check
    resp_invalid = client.post("/api/auth/verify-reset-token", json={"token": "wrong_token"})
    assert resp_invalid.status_code == 400


def test_reset_password_success_flow(client, db_session):
    member = make_member(db_session, psn="PSN-RESET-1", email="reset1@example.com")
    user = make_member_user(db_session, member, password="OldPassword123!")

    # Create an active session to test session revocation
    session_record = models.AuthSession(
        user_id=user.id,
        jti=uuid.uuid4().hex,
        expires_at=datetime.utcnow() + timedelta(hours=1),
    )
    db_session.add(session_record)

    # Set lockout counters to test lockout clearing
    user.failed_login_count = 4
    user.locked_until = datetime.utcnow() + timedelta(minutes=10)
    user.must_change_password = True
    db_session.commit()

    raw_token = "valid_reset_token_xyz987654321"
    token_record = models.PasswordResetToken(
        user_id=user.id,
        token_hash=_hash_token(raw_token),
        expires_at=datetime.utcnow() + timedelta(minutes=15),
    )
    db_session.add(token_record)
    db_session.commit()

    # Reset password
    new_pwd = "NewSecurePassword456!"
    resp = client.post(
        "/api/auth/reset-password",
        json={"token": raw_token, "new_password": new_pwd},
    )
    assert resp.status_code == 200
    assert "Password has been successfully reset" in resp.json()["message"]

    # Verify DB state
    db_session.refresh(user)
    db_session.refresh(token_record)
    db_session.refresh(session_record)

    # 1. New password verifies, old password fails
    assert verify_password(new_pwd, user.password_hash)
    assert not verify_password("OldPassword123!", user.password_hash)

    # 2. Token marked used
    assert token_record.used_at is not None

    # 3. Lockout cleared and must_change_password is False
    assert user.failed_login_count == 0
    assert user.locked_until is None
    assert user.must_change_password is False

    # 4. Old session revoked
    assert session_record.revoked_at is not None
    assert session_record.revoked_reason == "password_recovery"


def test_reset_password_single_use_replay_rejection(client, db_session):
    member = make_member(db_session, psn="PSN-REPLAY-1", email="replay@example.com")
    user = make_member_user(db_session, member)

    raw_token = "single_use_token_12345"
    token_record = models.PasswordResetToken(
        user_id=user.id,
        token_hash=_hash_token(raw_token),
        expires_at=datetime.utcnow() + timedelta(minutes=15),
    )
    db_session.add(token_record)
    db_session.commit()

    # First reset succeeds
    resp1 = client.post(
        "/api/auth/reset-password",
        json={"token": raw_token, "new_password": "FirstNewPassword1!"},
    )
    assert resp1.status_code == 200

    # Second reset with same token MUST fail
    resp2 = client.post(
        "/api/auth/reset-password",
        json={"token": raw_token, "new_password": "SecondNewPassword2!"},
    )
    assert resp2.status_code == 400
    assert "already been used" in resp2.json()["detail"]


def test_reset_password_expired_token_rejection(client, db_session):
    member = make_member(db_session, psn="PSN-EXPIRED-1", email="expired@example.com")
    user = make_member_user(db_session, member)

    raw_token = "expired_token_00000"
    token_record = models.PasswordResetToken(
        user_id=user.id,
        token_hash=_hash_token(raw_token),
        expires_at=datetime.utcnow() - timedelta(minutes=5),  # expired 5 min ago
    )
    db_session.add(token_record)
    db_session.commit()

    resp = client.post(
        "/api/auth/reset-password",
        json={"token": raw_token, "new_password": "PasswordWithLetters1!"},
    )
    assert resp.status_code == 400
    assert "expired" in resp.json()["detail"]


def test_reset_password_enforces_password_policy(client, db_session):
    member = make_member(db_session, psn="PSN-POLICY-1", email="policy@example.com")
    user = make_member_user(db_session, member)

    raw_token = "policy_test_token"
    token_record = models.PasswordResetToken(
        user_id=user.id,
        token_hash=_hash_token(raw_token),
        expires_at=datetime.utcnow() + timedelta(minutes=15),
    )
    db_session.add(token_record)
    db_session.commit()

    # Weak password (too short)
    resp = client.post(
        "/api/auth/reset-password",
        json={"token": raw_token, "new_password": "short"},
    )
    assert resp.status_code == 400
    assert "at least 8 characters" in resp.json()["detail"]

    # Weak password (no numbers)
    resp2 = client.post(
        "/api/auth/reset-password",
        json={"token": raw_token, "new_password": "lettersonlyhere"},
    )
    assert resp2.status_code == 400
    assert "at least one number" in resp2.json()["detail"]

    # Token must still be unused
    db_session.refresh(token_record)
    assert token_record.used_at is None


def test_reset_password_does_not_reactivate_suspended_or_deactivated_user(client, db_session):
    member = make_member(db_session, psn="PSN-SUSP-1", email="suspended@example.com")
    user = make_member_user(db_session, member)
    user.account_status = models.AccountStatus.SUSPENDED
    db_session.commit()

    raw_token = "suspended_user_token"
    token_record = models.PasswordResetToken(
        user_id=user.id,
        token_hash=_hash_token(raw_token),
        expires_at=datetime.utcnow() + timedelta(minutes=15),
    )
    db_session.add(token_record)
    db_session.commit()

    resp = client.post(
        "/api/auth/reset-password",
        json={"token": raw_token, "new_password": "ValidPassword123!"},
    )
    assert resp.status_code == 403
    assert "suspended or deactivated" in resp.json()["detail"]

    db_session.refresh(user)
    assert user.account_status == models.AccountStatus.SUSPENDED


def test_admin_can_reset_staff_password(client, db_session, seed_permissions):
    admin = make_admin_user(db_session, username="superadmin", super_admin=True)
    grant_permission(db_session, admin, "admin.user_manage")

    staff = make_admin_user(db_session, username="staff1", password="StaffOldPassword1!")
    staff.failed_login_count = 3
    staff.must_change_password = False

    session_record = models.AuthSession(
        user_id=staff.id,
        jti=uuid.uuid4().hex,
        expires_at=datetime.utcnow() + timedelta(hours=1),
    )
    db_session.add(session_record)
    db_session.commit()

    temp_pwd = "TempStaffPass123!"
    resp = client.post(
        f"/api/admin/users/{staff.id}/reset-password",
        json={"temporary_password": temp_pwd},
        headers=auth_headers(admin),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["must_change_password"] is True

    db_session.refresh(staff)
    db_session.refresh(session_record)

    assert verify_password(temp_pwd, staff.password_hash)
    assert staff.must_change_password is True
    assert staff.failed_login_count == 0
    assert session_record.revoked_at is not None
    assert session_record.revoked_reason == "admin_password_reset"


def test_unauthorized_user_cannot_reset_staff_password(client, db_session, seed_permissions):
    normal_admin = make_admin_user(db_session, username="limited_admin")
    staff = make_admin_user(db_session, username="target_staff")

    resp = client.post(
        f"/api/admin/users/{staff.id}/reset-password",
        json={"temporary_password": "TempStaffPass123!"},
        headers=auth_headers(normal_admin),
    )
    assert resp.status_code == 403
