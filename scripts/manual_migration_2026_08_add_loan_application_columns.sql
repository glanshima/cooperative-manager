-- Run this once in Neon's SQL Editor before redeploying the backend.
--
-- Why this is needed: the app auto-creates any MISSING TABLES on startup
-- (Base.metadata.create_all()), so the new `users`, `loan_applications`,
-- and `settings` tables will appear automatically on first deploy after
-- this change -- no action needed for those.
--
-- But `members` and `loan_types` already exist in your database with real
-- data, and create_all() does NOT add missing COLUMNS to tables that
-- already exist. Run this manually first, or every request touching these
-- new fields will fail with "column does not exist".

ALTER TABLE members
    ADD COLUMN IF NOT EXISTS loan_restricted BOOLEAN NOT NULL DEFAULT false;

ALTER TABLE members
    ADD COLUMN IF NOT EXISTS restriction_reason VARCHAR;

ALTER TABLE loan_types
    ADD COLUMN IF NOT EXISTS open_for_application BOOLEAN NOT NULL DEFAULT false;

-- Nothing else to do here -- flat_charge on loan_types was already added
-- in an earlier session before any loan_types rows existed, so it's not
-- repeated here. If you're unsure whether it's present, this is harmless
-- to run too:
ALTER TABLE loan_types
    ADD COLUMN IF NOT EXISTS flat_charge NUMERIC(14, 2) NOT NULL DEFAULT 0;
