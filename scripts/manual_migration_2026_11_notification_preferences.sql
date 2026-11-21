-- Notification email preferences (2026-11-21)
--
-- One row per account that changed its optional email switches. A
-- missing row means every optional email is on, so an empty table is
-- the correct default state.
--
-- Only categories whose email is genuinely optional have a column.
-- Account and security notices are always delivered and have no
-- preference.
--
-- IDEMPOTENT: re-running is a no-op. `Base.metadata.create_all()` also
-- creates this table on startup; this file keeps the sandbox /
-- Neon-branch flows and the production schema explicit and in step
-- with the model.

CREATE TABLE IF NOT EXISTS notification_preferences (
    user_id UUID NOT NULL PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    email_loan BOOLEAN NOT NULL DEFAULT TRUE,
    email_repayment BOOLEAN NOT NULL DEFAULT TRUE,
    updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL
);
