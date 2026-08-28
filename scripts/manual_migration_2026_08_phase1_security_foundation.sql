-- MACT Cooperative Manager -- Phase 1 (Security, Authorization, Audit &
-- Data Integrity Foundations) schema migration.
--
-- Run this once in Neon's SQL Editor BEFORE redeploying the backend, then
-- run scripts/seed_permissions.py, then (if you have an existing admin
-- account from before this phase) run the backfill statement at the
-- bottom to make it a Super Admin so it doesn't lose access.
--
-- This migration is purely additive (new tables + new nullable/defaulted
-- columns on `users`) -- no existing column is dropped or narrowed, and
-- no existing row's data is destroyed, per Section 25/16.

-- ---------------------------------------------------------------------
-- 1. Extend `users` with account lifecycle, lockout tracking, and the
--    super-admin escape hatch.
-- ---------------------------------------------------------------------

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'accountstatus') THEN
        CREATE TYPE accountstatus AS ENUM ('pending', 'active', 'suspended', 'deactivated');
    END IF;
END $$;

ALTER TABLE users
    ADD COLUMN IF NOT EXISTS account_status accountstatus NOT NULL DEFAULT 'active';
ALTER TABLE users
    ADD COLUMN IF NOT EXISTS status_reason VARCHAR;
ALTER TABLE users
    ADD COLUMN IF NOT EXISTS status_changed_at TIMESTAMP;
ALTER TABLE users
    ADD COLUMN IF NOT EXISTS status_changed_by_user_id UUID REFERENCES users(id);
ALTER TABLE users
    ADD COLUMN IF NOT EXISTS is_super_admin BOOLEAN NOT NULL DEFAULT false;
ALTER TABLE users
    ADD COLUMN IF NOT EXISTS failed_login_count INTEGER NOT NULL DEFAULT 0;
ALTER TABLE users
    ADD COLUMN IF NOT EXISTS locked_until TIMESTAMP;
ALTER TABLE users
    ADD COLUMN IF NOT EXISTS last_login_at TIMESTAMP;
ALTER TABLE users
    ADD COLUMN IF NOT EXISTS last_failed_login_at TIMESTAMP;

-- Backfill: any existing deactivated account (is_active = false) should
-- carry that forward into account_status rather than defaulting to
-- 'active' above.
UPDATE users SET account_status = 'deactivated' WHERE is_active = false;

-- ---------------------------------------------------------------------
-- 2. Office / Role / Permission / UserRoleAssignment
-- ---------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS offices (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR NOT NULL UNIQUE,
    description VARCHAR,
    is_active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMP NOT NULL DEFAULT now(),
    updated_at TIMESTAMP NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_offices_name ON offices (name);

CREATE TABLE IF NOT EXISTS permissions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    code VARCHAR NOT NULL UNIQUE,
    category VARCHAR NOT NULL,
    description VARCHAR NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_permissions_code ON permissions (code);

CREATE TABLE IF NOT EXISTS roles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR NOT NULL UNIQUE,
    description VARCHAR,
    is_active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMP NOT NULL DEFAULT now(),
    updated_at TIMESTAMP NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_roles_name ON roles (name);

CREATE TABLE IF NOT EXISTS role_permissions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    role_id UUID NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
    permission_id UUID NOT NULL REFERENCES permissions(id) ON DELETE CASCADE,
    CONSTRAINT uq_role_permission UNIQUE (role_id, permission_id)
);

CREATE TABLE IF NOT EXISTS user_role_assignments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role_id UUID NOT NULL REFERENCES roles(id),
    office_id UUID REFERENCES offices(id),
    is_active BOOLEAN NOT NULL DEFAULT true,
    assigned_at TIMESTAMP NOT NULL DEFAULT now(),
    assigned_by_user_id UUID REFERENCES users(id),
    revoked_at TIMESTAMP,
    revoked_by_user_id UUID REFERENCES users(id)
);
CREATE INDEX IF NOT EXISTS ix_user_role_assignments_user ON user_role_assignments (user_id);

-- ---------------------------------------------------------------------
-- 3. Auth sessions (real logout / server-side revocation)
-- ---------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS auth_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    jti VARCHAR NOT NULL UNIQUE,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    issued_at TIMESTAMP NOT NULL DEFAULT now(),
    expires_at TIMESTAMP NOT NULL,
    ip_address VARCHAR,
    user_agent VARCHAR,
    revoked_at TIMESTAMP,
    revoked_reason VARCHAR
);
CREATE INDEX IF NOT EXISTS ix_auth_sessions_jti ON auth_sessions (jti);

-- ---------------------------------------------------------------------
-- 4. Audit trail
-- ---------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS audit_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    actor_user_id UUID REFERENCES users(id),
    actor_username VARCHAR,
    actor_office_name VARCHAR,
    actor_role_names VARCHAR,
    event_type VARCHAR NOT NULL,
    entity_type VARCHAR,
    entity_id VARCHAR,
    action VARCHAR NOT NULL,
    previous_values JSONB,
    new_values JSONB,
    reason VARCHAR,
    ip_address VARCHAR,
    user_agent VARCHAR,
    request_reference VARCHAR,
    "timestamp" TIMESTAMP NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_audit_events_actor_user_id ON audit_events (actor_user_id);
CREATE INDEX IF NOT EXISTS ix_audit_events_event_type ON audit_events (event_type);
CREATE INDEX IF NOT EXISTS ix_audit_events_entity_type ON audit_events (entity_type);
CREATE INDEX IF NOT EXISTS ix_audit_events_entity_id ON audit_events (entity_id);
CREATE INDEX IF NOT EXISTS ix_audit_events_timestamp ON audit_events ("timestamp");
CREATE INDEX IF NOT EXISTS ix_audit_events_entity ON audit_events (entity_type, entity_id);

-- No UPDATE/DELETE grant hardening is included in this migration --
-- that's a Phase 10 (Production Hardening) deployment-role concern, not
-- a Phase 1 code/schema change. The application code itself never issues
-- UPDATE/DELETE against this table (see audit_service.py).

-- ---------------------------------------------------------------------
-- 5. Idempotency foundation
-- ---------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS idempotency_records (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id),
    endpoint VARCHAR NOT NULL,
    idempotency_key VARCHAR NOT NULL,
    request_hash VARCHAR NOT NULL,
    status_code INTEGER,
    response_body JSONB,
    completed_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT now(),
    CONSTRAINT uq_idempotency_scope UNIQUE (user_id, endpoint, idempotency_key)
);

-- ---------------------------------------------------------------------
-- 6. Post-migration verification queries (run manually, not part of the
--    migration itself -- included here for convenience)
-- ---------------------------------------------------------------------
-- SELECT count(*) FROM users WHERE account_status IS NULL;              -- expect 0
-- SELECT username, is_active, account_status FROM users ORDER BY username;
-- SELECT to_regclass('offices'), to_regclass('roles'), to_regclass('permissions'),
--        to_regclass('role_permissions'), to_regclass('user_role_assignments'),
--        to_regclass('auth_sessions'), to_regclass('audit_events'),
--        to_regclass('idempotency_records');                            -- expect all non-null

-- ---------------------------------------------------------------------
-- 7. IMPORTANT -- backward-compatibility backfill for pre-existing admins
-- ---------------------------------------------------------------------
-- Every admin account that existed before this migration had full,
-- undifferentiated access (the app's only prior authorization mechanism
-- was role = 'admin'). To preserve that existing functionality exactly
-- (Phase 1 Section 4) rather than silently locking these accounts out of
-- endpoints that now require a granular permission via the new
-- Office/Role/Permission model, mark them all as Super Admin. New admin
-- accounts created AFTER this migration will NOT get this treatment --
-- they must be explicitly granted a role. This is a deliberate
-- Change-Control decision (see report item C-1), not an oversight.
UPDATE users SET is_super_admin = true WHERE role = 'admin';
