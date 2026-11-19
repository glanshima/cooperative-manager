-- Cooperative branding in settings (2026-11-18)
--
-- The cooperative's own identity (name, short name, monogram and uploaded
-- logo) becomes editable from the Settings screen instead of being fixed
-- in the frontend constants. Koperra stays the platform credit and is not
-- stored per cooperative.
--
-- ADDITIVE + IDEMPOTENT: every column is only added when missing, and the
-- defaults match the constants that shipped before this change, so
-- existing rows keep their current appearance without a backfill and
-- re-running the file is a no-op.
--
-- The logo itself lives in Vercel Blob; `logo_url` is the public,
-- cacheable URL the frontend renders. Replacing or removing a logo deletes
-- the old blob by that URL, so no separate pathname column is needed.

ALTER TABLE settings ADD COLUMN IF NOT EXISTS cooperative_name VARCHAR(120) NOT NULL DEFAULT 'MACT Cooperative';
ALTER TABLE settings ADD COLUMN IF NOT EXISTS cooperative_short_name VARCHAR(32) NOT NULL DEFAULT 'MACT';
ALTER TABLE settings ADD COLUMN IF NOT EXISTS cooperative_monogram VARCHAR(8) NOT NULL DEFAULT 'M';
ALTER TABLE settings ADD COLUMN IF NOT EXISTS logo_url VARCHAR(500);
