-- In-app notifications (2026-11-19)
--
-- One row per notice shown to one user account (the member's own login,
-- for now). Rows are written in the same transaction as the state change
-- they announce; the title/body are stored as final rendered text.
--
-- IDEMPOTENT: the enum, table and index are created only when missing, so
-- re-running the file is a no-op. `Base.metadata.create_all()` also
-- creates this table on startup, which is why no backfill is needed --
-- this file keeps the sandbox / Neon-branch flows and the production
-- schema explicit and in step with the model.

DO $$
BEGIN
    CREATE TYPE notificationcategory AS ENUM (
        'loan',
        'repayment',
        'contribution',
        'account',
        'system'
    );
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

CREATE TABLE IF NOT EXISTS notifications (
    id UUID NOT NULL PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    category notificationcategory NOT NULL,
    title VARCHAR(200) NOT NULL,
    body VARCHAR(1000),
    link_path VARCHAR(255),
    is_read BOOLEAN NOT NULL DEFAULT FALSE,
    read_at TIMESTAMP WITHOUT TIME ZONE,
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL
);

-- The bell asks for "this user's newest notices" on every poll; the
-- descending order in the index matches that query exactly.
CREATE INDEX IF NOT EXISTS ix_notifications_user_created
    ON notifications (user_id, created_at DESC);
