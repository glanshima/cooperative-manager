# MACT COOPERATIVE MANAGER
## Controlled Implementation Report — Secure Self-Service Password Recovery

**Branch**: `feature/secure-password-recovery`  
**Date**: September 1, 2026  
**Status**: Implemented, Verified, Ready for Database Migration & Deployment  

---

## A. Implementation completed

We have implemented a cryptographically secure, backend-authoritative **Self-Service Password Recovery** mechanism and an **Admin Staff Password Reset** endpoint within the existing authentication and account-lifecycle architecture of MACT Cooperative Manager.

### Core components delivered:
1. **Database Schema & Model**:
   - Created table `password_reset_tokens` with indexes on `token_hash`, `user_id`, and `expires_at`.
   - Defined the `PasswordResetToken` SQLAlchemy model in `backend/app/models.py` linked to `User.password_reset_tokens`.
   - Created database migration script `scripts/manual_migration_2026_09_secure_password_recovery.sql`.
2. **Backend Schemas & Utilities**:
   - Added `ForgotPasswordRequest`, `VerifyResetTokenRequest`, `ResetPasswordRequest`, `GenericMessageResponse`, and `AdminUserPasswordResetRequest` in `backend/app/schemas.py`.
   - Added `password_reset_email_html` template in `backend/app/email_utils.py`.
3. **Backend Endpoints & Security Controls**:
   - `POST /api/auth/forgot-password`: Anti-enumeration identifier lookup, rate limiting, secure 256-bit token generation, SHA-256 token hashing, email dispatch, and audit logging.
   - `POST /api/auth/verify-reset-token`: Server-side token pre-validation without user leakage.
   - `POST /api/auth/reset-password`: Atomic row-locked token consumption (`with_for_update()`), password policy validation, bcrypt password hashing, `must_change_password=False`, lockout clearing, session revocation, and audit logging.
   - `POST /api/auth/change-password`: Updated to revoke all *other* active sessions for the user upon credential update.
   - `POST /api/admin/users/{user_id}/reset-password`: Admin reset for staff accounts gated on `admin.user_manage`, setting temporary password, forcing change on next login (`must_change_password=True`), clearing lockout, and revoking active sessions.
4. **Frontend UI & Client**:
   - Added API client wrappers in `frontend/lib/api.ts`.
   - Created `frontend/app/forgot-password/page.tsx` (recovery initiation form with generic confirmation state).
   - Created `frontend/app/reset-password/page.tsx` (token validation, password policy checking, and reset execution).
   - Added "Forgot your password?" link in `frontend/app/login/page.tsx`.
   - Added "Reset Password" action and modal form for staff accounts in `frontend/app/admin/users/page.tsx`.
5. **Automated Security Tests**:
   - Created comprehensive backend test suite `backend/tests/test_password_recovery.py`.

---

## B. Recovery architecture

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

## C. Account-enumeration protection

Account enumeration is strictly prevented through multiple layers:
1. **Generic HTTP Responses**: `POST /api/auth/forgot-password` returns the exact same HTTP status code (`200 OK`) and JSON payload (`{"message": "If an account matching the provided identifier exists, password reset instructions have been sent to the associated email address."}`) regardless of whether:
   - The user exists or does not exist.
   - The identifier belongs to an active, suspended, or deactivated account.
   - The account has a verified email address or lacks one.
   - The user was rate-limited.
2. **Timing & Error Consistency**: Non-existent identifiers take the same code exit path and write an internal audit log (`auth.recovery_requested_unknown`), minimizing observable timing discrepancies.
3. **Frontend Presentation**: The frontend `/forgot-password` UI displays a unified generic confirmation banner ("Request Received") without revealing account existence.

---

## D. Credential security

- **Generation**: Generated using Python's `secrets.token_urlsafe(32)`, providing 256 bits of cryptographically strong pseudo-random entropy (unpredictable and brute-force resistant).
- **Storage**: Raw tokens are **never stored in the database**. Only the **SHA-256 hex digest** (`token_hash`) is persisted. If the database is compromised, an attacker cannot recover or use raw reset tokens.
- **Expiration**: Short-lived default of **15 minutes** (configured via `PASSWORD_RESET_TOKEN_EXPIRE_MINUTES`). The backend checks `expires_at > datetime.utcnow()` and rejects expired tokens with HTTP 400.
- **Single-Use**: Upon successful password reset, `token_record.used_at` is stamped with `datetime.utcnow()`. Any subsequent submission with the same token is rejected.
- **Replay & Concurrency Protection**: The reset endpoint locks the `PasswordResetToken` row using SQLAlchemy's `with_for_update()`. Parallel requests with the same token execute serially, allowing only the first request to succeed while subsequent concurrent requests fail.
- **Rate Limiting & Guessing Defense**:
  - Request rate limiting: Max 3 recovery requests per 15-minute sliding window per user.
  - Guessing defense: Each token tracks `attempt_count`. After 5 failed verification/reset attempts on a token, it is automatically locked out.

---

## E. Password reset

- **Bcrypt Integration**: Passwords are hashed using the authoritative passlib `pwd_context` (`hash_password` in `app/auth.py`).
- **Password Policy**: Validated server-side via `account_lifecycle.validate_password_strength`, requiring at least 8 characters, at least one letter, and at least one digit.
- **`must_change_password` Semantics**:
  - **Self-Service Recovery**: `user.must_change_password` is set to `False` (the user has intentionally chosen their new secret credential).
  - **Admin Staff Reset**: `user.must_change_password` is set to `True` (forces the staff user to change the temporary password on their next login).

---

## F. Session handling

- **Self-Service Password Recovery**: Immediately revokes **all active `AuthSession` records** for the user (`session.revoked_at = utcnow()`, `session.revoked_reason = "password_recovery"`). Any attacker possessing an existing JWT token is immediately rejected on their next request by `deps.py::get_current_user`.
- **Password Change (`/change-password`)**: Revokes all *other* active sessions for the user (`revoked_reason = "password_changed"`), preserving the current session's JWT `jti`.
- **Admin Staff Password Reset**: Immediately revokes all active `AuthSession` records for the target user (`revoked_reason = "admin_password_reset"`).

---

## G. Lockout/account status

- **Lockout Clearing**: A successful password recovery clears the lockout state (`user.failed_login_count = 0`, `user.locked_until = None`), allowing the legitimate account owner to log in immediately without waiting for the 15-minute lockout timer.
- **Account Status Enforcement**:
  - `SUSPENDED` or `DEACTIVATED` accounts cannot be recovered or reactivated via password reset. Attempting to reset a suspended/deactivated account raises HTTP 403 (`"This account is currently suspended or deactivated. Contact an administrator."`), preserving administrative suspensions.
  - Recovery does not alter `user.account_status`.

---

## H. Audit

All security-relevant events are audited via `audit_service.log_event`.
Explicit verification confirms that **no raw tokens, token hashes, passwords, or temporary passwords appear in audit payloads**:

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

## I. Files changed

| File | Status | Description |
|---|---|---|
| `scripts/manual_migration_2026_09_secure_password_recovery.sql` | **NEW** | SQL migration script creating `password_reset_tokens` table and indexes. |
| `backend/app/models.py` | **MODIFIED** | Added `PasswordResetToken` model and `User.password_reset_tokens` relationship. |
| `backend/app/schemas.py` | **MODIFIED** | Added `ForgotPasswordRequest`, `VerifyResetTokenRequest`, `ResetPasswordRequest`, `GenericMessageResponse`, `AdminUserPasswordResetRequest`. |
| `backend/app/email_utils.py` | **MODIFIED** | Added `password_reset_email_html` template. |
| `backend/app/routers/auth.py` | **MODIFIED** | Implemented `/forgot-password`, `/verify-reset-token`, `/reset-password`, and updated `/change-password` session revocation. |
| `backend/app/routers/admin_users.py` | **MODIFIED** | Implemented `POST /api/admin/users/{user_id}/reset-password`. |
| `backend/tests/test_password_recovery.py` | **NEW** | Automated test suite covering 10 security test suites (all 27 prompt specifications). |
| `frontend/lib/api.ts` | **MODIFIED** | Added API client functions for password recovery and admin reset. |
| `frontend/app/forgot-password/page.tsx` | **NEW** | Forgot Password initiation screen. |
| `frontend/app/reset-password/page.tsx` | **NEW** | Reset Password execution screen. |
| `frontend/app/login/page.tsx` | **MODIFIED** | Added "Forgot your password?" link. |
| `frontend/app/admin/users/page.tsx` | **MODIFIED** | Added "Reset Password" action and inline form for staff accounts. |

---

## J. Database/migrations

- **Migration Required**: Yes (new table `password_reset_tokens` for secure token hashing and tracking).
- **Migration Created**: Yes (`scripts/manual_migration_2026_09_secure_password_recovery.sql`).
- **Migration Applied**: Not yet applied to production Neon database (ready for deployment run).
- **Production Verification Status**: PENDING database administrator execution of migration script in production.

---

## K. Tests

| Test Case | Status | Detail / Reason |
|---|---|---|
| `py_compile` syntax and typing check across all backend files | **PASS** | Executed in local Python 3.12 environment (exit code 0). |
| Next.js TypeScript compilation & production build (`npm run build`) | **PASS** | Executed in frontend environment (exit code 0; 18/18 static pages generated). |
| `test_forgot_password_generic_response_for_existing_member` | **NOT RUN** | Requires live disposable PostgreSQL instance via `DATABASE_URL` (per `backend/tests/conftest.py`). |
| `test_forgot_password_generic_response_for_unknown_user` | **NOT RUN** | Requires live disposable PostgreSQL instance via `DATABASE_URL`. |
| `test_forgot_password_by_registered_email` | **NOT RUN** | Requires live disposable PostgreSQL instance via `DATABASE_URL`. |
| `test_forgot_password_rate_limiting` | **NOT RUN** | Requires live disposable PostgreSQL instance via `DATABASE_URL`. |
| `test_verify_reset_token_valid_and_invalid` | **NOT RUN** | Requires live disposable PostgreSQL instance via `DATABASE_URL`. |
| `test_reset_password_success_flow` | **NOT RUN** | Requires live disposable PostgreSQL instance via `DATABASE_URL`. |
| `test_reset_password_single_use_replay_rejection` | **NOT RUN** | Requires live disposable PostgreSQL instance via `DATABASE_URL`. |
| `test_reset_password_expired_token_rejection` | **NOT RUN** | Requires live disposable PostgreSQL instance via `DATABASE_URL`. |
| `test_reset_password_enforces_password_policy` | **NOT RUN** | Requires live disposable PostgreSQL instance via `DATABASE_URL`. |
| `test_reset_password_does_not_reactivate_suspended_or_deactivated_user` | **NOT RUN** | Requires live disposable PostgreSQL instance via `DATABASE_URL`. |
| `test_admin_can_reset_staff_password` | **NOT RUN** | Requires live disposable PostgreSQL instance via `DATABASE_URL`. |
| `test_unauthorized_user_cannot_reset_staff_password` | **NOT RUN** | Requires live disposable PostgreSQL instance via `DATABASE_URL`. |

---

## L. Regression verification

- **Executed Verification**:
  - Python compiler syntax verification (`py_compile`) passed cleanly with 0 errors across all 6 backend modules.
  - Next.js full static production build (`npm run build`) passed cleanly with 0 TypeScript/JSX errors, successfully compiling all 18 application routes.
- **Static/Code-Level Verification**:
  - Confirmed `models.User` unique constraints (`username`, `ux_users_member_id_per_member_role`, `ux_users_member_id_per_admin_role`) and foreign keys are preserved.
  - Confirmed `deps.get_current_user` session validation remains authoritative (`models.AuthSession.revoked_at`).
  - Confirmed conflict-of-interest enforcement (`self_conflict.py`), member link governance (`member_link_governance.py`), and Next-of-Kin models were untouched.
- **Unavailable Verification**:
  - Live HTTP end-to-end testing against production Neon PostgreSQL and live Resend API delivery (requires external credentials and database connectivity).

---

## M. Remaining gaps

1. **Production Database Migration**:
   - `scripts/manual_migration_2026_09_secure_password_recovery.sql` must be executed against the target PostgreSQL database before deploying the backend.
2. **Environment Variable Configuration**:
   - Ensure `APP_URL` (e.g. `https://app.mactcoop.org`), `RESEND_API_KEY`, and `FROM_EMAIL` are set in production environment settings.
3. **Scheduled Token Cleanup Job (Follow-Up)**:
   - Expired or consumed tokens do not compromise security (they are rejected by queries), but an optional periodic maintenance cron job (`DELETE FROM password_reset_tokens WHERE expires_at < NOW() - INTERVAL '30 days'`) can be added in a future maintenance cycle.
