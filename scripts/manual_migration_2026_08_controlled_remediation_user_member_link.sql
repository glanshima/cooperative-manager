-- MACT Cooperative Manager -- Controlled Phase 1 Remediation
-- User <-> Member conflict-of-interest link (Sections 1 and 9).
--
-- BACKGROUND: users.member_id already existed (added in the original
-- Phase 1 security-foundation migration) as a nullable FK to members.id,
-- with a single table-wide UNIQUE constraint. That constraint was
-- written assuming member_id would only ever be populated for
-- role='member' (self-service login) accounts. This migration relaxes
-- that constraint so an ADMIN-role account can ALSO legitimately link to
-- the same member_id as that person's separate member-role self-service
-- account (an elected EXCO officer both self-serves as a member under
-- one login and acts with admin authority under another) -- while still
-- preventing two rows of the SAME role from ambiguously claiming the
-- same member_id.
--
-- This migration does NOT add a new column (member_id already exists)
-- and does NOT populate member_id for any existing account -- per the
-- remediation prompt's explicit instruction, existing users are never
-- auto-mapped to a member by inference. Every admin account's
-- member_id remains NULL after this migration until a human explicitly
-- sets it via the admin-users API (see routers/admin_users.py).
--
-- SAFE-MIGRATION PROCEDURE:
--   1. Run the pre-flight check in Part 1. It must return 0 rows before
--      proceeding -- if it doesn't, STOP: there is already more than one
--      user of the same role pointing at the same member_id, which the
--      new partial unique indexes would reject. That would mean bad data
--      already exists and needs manual review before this migration is
--      safe to apply; do not force the index anyway.
--   2. Run Part 2 to drop the old table-wide unique constraint.
--   3. Run Part 3 to add the two new partial unique indexes.
--   4. Run Part 4 to verify.

-- ---------------------------------------------------------------------
-- Part 1 -- pre-flight check. Must return 0 rows.
-- ---------------------------------------------------------------------
SELECT member_id, role, count(*) AS n
FROM users
WHERE member_id IS NOT NULL
GROUP BY member_id, role
HAVING count(*) > 1;

-- ---------------------------------------------------------------------
-- Part 2 -- drop the old table-wide unique constraint on member_id.
-- Written defensively (looks up the actual constraint name rather than
-- assuming it) since this table predates the migration-script era of
-- this project and its exact original constraint name isn't recorded
-- anywhere in scripts/.
-- ---------------------------------------------------------------------
DO $$
DECLARE
    constraint_name text;
BEGIN
    SELECT con.conname INTO constraint_name
    FROM pg_constraint con
    JOIN pg_class rel ON rel.oid = con.conrelid
    JOIN pg_attribute att ON att.attrelid = rel.oid AND att.attnum = ANY(con.conkey)
    WHERE rel.relname = 'users'
      AND con.contype = 'u'
      AND att.attname = 'member_id'
      AND array_length(con.conkey, 1) = 1;

    IF constraint_name IS NOT NULL THEN
        EXECUTE format('ALTER TABLE users DROP CONSTRAINT %I', constraint_name);
        RAISE NOTICE 'Dropped old unique constraint % on users.member_id', constraint_name;
    ELSE
        RAISE NOTICE 'No table-wide unique constraint found on users.member_id -- nothing to drop (already migrated, or it was never a plain UNIQUE column).';
    END IF;
END $$;

-- Also drop a plain unique INDEX if one exists on member_id instead of a
-- named constraint (SQLAlchemy's unique=True can materialize as either,
-- depending on how the table was originally created).
DROP INDEX IF EXISTS users_member_id_key;
DROP INDEX IF EXISTS ix_users_member_id;

-- ---------------------------------------------------------------------
-- Part 3 -- add the two role-scoped partial unique indexes.
-- ---------------------------------------------------------------------
CREATE UNIQUE INDEX IF NOT EXISTS ux_users_member_id_per_member_role
    ON users (member_id)
    WHERE role = 'member';

CREATE UNIQUE INDEX IF NOT EXISTS ux_users_member_id_per_admin_role
    ON users (member_id)
    WHERE role = 'admin';

-- ---------------------------------------------------------------------
-- Part 4 -- verification
-- ---------------------------------------------------------------------
-- SELECT indexname, indexdef FROM pg_indexes
--        WHERE tablename = 'users' AND indexname LIKE 'ux_users_member_id%';
--        -- expect 2 rows
-- SELECT conname FROM pg_constraint
--        WHERE conrelid = 'users'::regclass AND contype = 'u';
--        -- expect the old member_id unique constraint (if any existed) to be gone;
--        -- users_username_key should still be present (unrelated column)
