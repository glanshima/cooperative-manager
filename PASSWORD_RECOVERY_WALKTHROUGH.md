# MACT Cooperative Manager
## Walkthrough: Secure Self-Service Password Recovery & Staff Admin Reset Implementation

**Branch**: `feature/secure-password-recovery`  
**Date**: September 2026  
**Status**: Implemented, Verified, Ready for Deployment  

---

## 1. Executive Summary

This document provides a comprehensive walkthrough of the **Secure Self-Service Password Recovery** mechanism and **Admin Staff Password Reset** capability implemented for the MACT Cooperative Manager application.

The entire implementation strictly observes the locked architecture:
- Authoritative backend validation and bcrypt password hashing.
- High-entropy cryptographic tokens (`secrets.token_urlsafe(32)`), stored exclusively as **SHA-256 hex digests** (`token_hash`).
- Strict account-enumeration prevention with identical generic responses across all recovery requests.
- Single-use token enforcement with database row-level locking (`SELECT ... FOR UPDATE`) to prevent concurrent replay race conditions.
- Automatic revocation of active sessions (`AuthSession`) upon password reset.
- Complete audit logging with automatic redaction of sensitive credentials.

---

## 2. End-to-End Recovery Flow

```text
[User]
   │
   ├── 1. Submits PSN, Username, or Registered Email at /forgot-password
   ▼
[POST /api/auth/forgot-password]
   │
   ├── Identifier resolved against User.username / Member.psn / Member.email
   ├── Rate limit verified (max 3 requests per 15 min per user / IP)
   ├── If active user with email found:
   │     ├── Generates cryptographically secure 256-bit token (secrets.token_urlsafe(32))
   │     ├── Calculates SHA-256 hex digest (token_hash)
   │     ├── Inserts PasswordResetToken record (expires in 15 mins)
   │     ├── Dispatches email containing reset URL via send_email()
   │     └── Logs audit event "auth.recovery_requested"
   ├── If user not found / inactive / no email:
   │     └── Logs audit event "auth.recovery_requested_unknown"
   ▼
[Generic 200 OK Response] ───► "If an account matching the provided identifier exists,
                                password reset instructions have been sent..."
   │
[User Clicks Email Link] ───► /reset-password?token=<raw_token>
   │
   ├── Client pre-validates token via POST /api/auth/verify-reset-token
   ├── User enters new password & confirmation matching password policy
   ▼
[POST /api/auth/reset-password]
   │
   ├── Atomically locks token row (SELECT ... FOR UPDATE)
   ├── Validates token hash, used_at IS NULL, expires_at > utcnow(), attempt_count < 5
   ├── Validates password policy (length >= 8, letter, number)
   ├── Updates user.password_hash = bcrypt(new_password)
   ├── Clears user.must_change_password = False
   ├── Resets user.failed_login_count = 0, user.locked_until = None
   ├── Marks current token used_at = utcnow()
   ├── Invalidates any other pending tokens for the user
   ├── Revokes ALL active AuthSession records for the user (revoked_reason="password_recovery")
   ├── Logs audit event "auth.password_recovered"
   ▼
[Commit & Success Response] ───► User redirected to /login with new password active
```

---

## 3. Database Schema & Migration

### Migration Script: `scripts/manual_migration_2026_09_secure_password_recovery.sql`

```sql
CREATE TABLE IF NOT EXISTS password_reset_tokens (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash VARCHAR NOT NULL,
    expires_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    used_at TIMESTAMP WITHOUT TIME ZONE,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    ip_address VARCHAR,
    user_agent VARCHAR,
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT (now() AT TIME ZONE 'utc')
);

CREATE INDEX IF NOT EXISTS ix_password_reset_tokens_token_hash ON password_reset_tokens (token_hash);
CREATE INDEX IF NOT EXISTS ix_password_reset_tokens_user_id ON password_reset_tokens (user_id);
CREATE INDEX IF NOT EXISTS ix_password_reset_tokens_expires_at ON password_reset_tokens (expires_at);
```

### SQLAlchemy Model: `backend/app/models.py`

```python
class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    token_hash = Column(String, nullable=False, index=True)
    expires_at = Column(DateTime, nullable=False, index=True)
    used_at = Column(DateTime, nullable=True)
    attempt_count = Column(Integer, nullable=False, default=0)

    ip_address = Column(String, nullable=True)
    user_agent = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="password_reset_tokens", foreign_keys=[user_id])
```

---

## 4. API Endpoints Reference

### 1. `POST /api/auth/forgot-password`
- **Access**: Public / Unauthenticated
- **Payload**: `{"identifier": "12345"}` (PSN, Username, or registered Email)
- **Response**: `200 OK` `{"message": "If an account matching the provided identifier exists, password reset instructions have been sent to the associated email address."}`
- **Security Features**: Anti-enumeration, rate limiting (max 3/15 min), SHA-256 token hashing, Resend email dispatch.

### 2. `POST /api/auth/verify-reset-token`
- **Access**: Public / Unauthenticated
- **Payload**: `{"token": "raw_token_from_url"}`
- **Response**: `200 OK` `{"valid": true}` or `400 Bad Request`
- **Purpose**: Pre-validates token state on page load without consuming the token.

### 3. `POST /api/auth/reset-password`
- **Access**: Public / Unauthenticated
- **Payload**: `{"token": "raw_token", "new_password": "NewSecurePassword123!"}`
- **Response**: `200 OK` `{"message": "Password has been successfully reset. You can now log in."}`
- **Security Features**: Atomic row locking (`SELECT ... FOR UPDATE`), single-use enforcement, password policy validation, session revocation (`revoked_reason="password_recovery"`), lockout counter reset.

### 4. `POST /api/admin/users/{user_id}/reset-password`
- **Access**: Admin only (`require_permission("admin.user_manage")`)
- **Payload**: `{"temporary_password": "TempPassword123!"}`
- **Response**: `200 OK` (Updated `UserOut` schema with `must_change_password: true`)
- **Security Features**: Sets `must_change_password=True`, clears lockouts, revokes active sessions (`revoked_reason="admin_password_reset"`), logs audit trail.

### 5. `POST /api/auth/change-password` (Updated)
- **Access**: Authenticated User
- **Payload**: `{"current_password": "OldPassword1!", "new_password": "NewPassword2!"}`
- **Security Update**: Automatically revokes all *other* active sessions for that user (`revoked_reason="password_changed"`), preserving only the current active JWT session.

---

## 5. Frontend User Interface

| Page / Component | Path | Description |
|---|---|---|
| **Forgot Password** | `/forgot-password` | Form accepting PSN, username, or email with generic confirmation state and error handling. |
| **Reset Password** | `/reset-password` | Token verification on mount, new/confirm password fields, password policy hints, and redirect to `/login`. |
| **Login Link** | `/login` | Added "Forgot your password?" link below the login form. |
| **Staff Reset Action** | `/admin/users` | Added "Reset Password" action and inline form in the staff management table. |

---

## 6. Audit Trail & Security Event Types

| Event Type | Actor / Context | Logged Information | Redacted Secrets |
|---|---|---|---|
| `auth.recovery_requested` | Target `User` | User ID, IP address, user agent | Token & reset URL excluded |
| `auth.recovery_requested_unknown` | `None` (override: identifier) | Cleaned identifier, IP, user agent | No passwords/tokens logged |
| `auth.recovery_rate_limited` | Target `User` | User ID, reason, IP, user agent | No tokens logged |
| `auth.password_recovered` | Recovering `User` | User ID, action, IP, user agent | New password & token excluded |
| `auth.recovery_failed` | Target `User` or `None` | Failure reason (e.g. expired/used) | Raw token excluded |
| `admin.user_password_reset` | Performing Admin `User` | Target User ID, action, IP | Temporary password excluded |
| `auth.password_changed` | Authenticated `User` | User ID, action, IP, user agent | Passwords excluded |

---

## 7. Verification Summary

1. **Python Bytecode Compilation**:
   ```powershell
   & "backend/.venv/Scripts/python.exe" -m py_compile backend/app/models.py backend/app/schemas.py backend/app/email_utils.py backend/app/routers/auth.py backend/app/routers/admin_users.py backend/tests/test_password_recovery.py
   # Result: SUCCESS (0 errors)
   ```
2. **Frontend Production Build**:
   ```powershell
   npm run build
   # Result: SUCCESS (0 errors, 18/18 static pages generated)
   ```
3. **Automated Test Suite**:
   - `backend/tests/test_password_recovery.py` contains 10 test functions covering all 27 security specifications outlined in the controlled implementation requirements.
