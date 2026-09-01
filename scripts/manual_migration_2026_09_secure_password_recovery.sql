-- Manual Migration: Secure Self-Service Password Recovery
-- Date: 2026-09-01
-- Description: Creates password_reset_tokens table for secure, short-lived,
--              single-use, hashed password recovery tokens.

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
