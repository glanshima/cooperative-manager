-- MACT Cooperative Manager -- Controlled Implementation
-- Admin Governance & Member-Link Enforcement (Sections 2-4)
--
-- BACKGROUND: the self-conflict guard (self_conflict.py) already
-- prevents a LINKED admin from acting on their own member record, but
-- nothing previously stopped an UNLINKED admin from being granted a
-- sensitive financial permission (loan.approve, disbursement.submit,
-- etc.) in the first place -- an account the self-conflict guard can
-- never actually check, because it has nothing to check it against.
--
-- This migration adds:
--   1. permissions.requires_member_link (bool, default false) --
--      code-defined classification, seeded/kept in sync by
--      scripts/seed_permissions.py from permissions_catalogue.py.
--   2. users.confirmed_non_member_admin (bool, default false) -- an
--      explicit, human-set attestation that an admin account does NOT
--      represent a cooperative member, set ONLY via
--      PATCH /api/admin/users/{id}/non-member-confirmation. Defaults
--      to false (fail-closed) for every existing and new row; this
--      migration does NOT set it true for any account, per the same
--      "never infer" rule as member_id itself.
--
-- After this migration, re-run scripts/seed_permissions.py so the
-- requires_member_link classification is actually populated on the
-- existing permissions rows (this migration only adds the column with
-- its default; it does not seed values).
--
-- SAFE-MIGRATION PROCEDURE:
--   1. Run Part 1 to add both columns.
--   2. Run Part 2 to verify.
--   3. Separately, run `python scripts/seed_permissions.py` against the
--      same database to populate requires_member_link on each
--      permission row from the catalogue.

-- ---------------------------------------------------------------------
-- Part 1 -- add the two columns.
-- ---------------------------------------------------------------------
ALTER TABLE permissions
    ADD COLUMN IF NOT EXISTS requires_member_link boolean NOT NULL DEFAULT false;

ALTER TABLE users
    ADD COLUMN IF NOT EXISTS confirmed_non_member_admin boolean NOT NULL DEFAULT false;

-- ---------------------------------------------------------------------
-- Part 2 -- verification
-- ---------------------------------------------------------------------
-- SELECT column_name, data_type, column_default FROM information_schema.columns
--        WHERE table_name = 'permissions' AND column_name = 'requires_member_link';
--        -- expect 1 row, default false
-- SELECT column_name, data_type, column_default FROM information_schema.columns
--        WHERE table_name = 'users' AND column_name = 'confirmed_non_member_admin';
--        -- expect 1 row, default false
-- SELECT code, requires_member_link FROM permissions ORDER BY category, code;
--        -- run AFTER seed_permissions.py -- sensitive codes (loan.approve,
--        -- disbursement.submit, etc.) should show true; others false
