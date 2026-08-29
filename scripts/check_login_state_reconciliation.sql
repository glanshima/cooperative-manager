-- MACT Cooperative Manager -- Login State Reconciliation Addendum
-- Read-only diagnostic. Run this against your live database to check
-- for any pre-existing data that the login-state fix (MemberOut's new
-- login_user_id/login_account_status fields, see members.py) can't
-- safely resolve on its own.
--
-- WHY THIS IS READ-ONLY, NOT A MIGRATION: every code path in this
-- repository that has ever created a User row for a member
-- (routers/auth.py's create_member_login; no data-migration script
-- under scripts/ ever creates User rows) has always set member_id at
-- creation time. So under normal operation there should be nothing to
-- backfill -- the Login State Reconciliation bug was in what the API/UI
-- SURFACED (MemberOut never exposed login state; the frontend rendered
-- "Create Login" unconditionally for every row), not in the underlying
-- data. This script exists to verify that assumption against your ACTUAL
-- data rather than just asserting it, and to catch the one scenario the
-- codebase can't rule out: a User row created through some out-of-band
-- mechanism (a manual SQL insert, a since-removed admin tool, etc.) that
-- bypassed create_member_login and left member_id unset or wrong.
--
-- Per Section 4/5 of the addendum: if any of the queries below return
-- rows, do NOT auto-link them by guessing from name/email/phone. Each
-- flagged row needs a human to confirm the right member_id (or confirm
-- there isn't one) via the admin-users member-link endpoint
-- (PATCH /api/admin/users/{user_id}/member-link) or, for a genuine
-- member self-service login, by direct, verified administrative
-- correction -- there is no automatic fix for this file to apply.

-- 1. Member-role User rows with NO member_id at all. In a healthy
--    database this returns 0 rows -- every member-role login has always
--    been created with member_id set. Any row here is a genuine
--    orphaned login needing manual reconciliation.
SELECT id, username, account_status, created_at
FROM users
WHERE role = 'member' AND member_id IS NULL;

-- 2. Member-role User rows whose member_id points at a Member that no
--    longer exists (should be impossible given the FK, but check
--    anyway in case of a historical row predating the constraint).
SELECT u.id, u.username, u.member_id
FROM users u
LEFT JOIN members m ON m.id = u.member_id
WHERE u.role = 'member' AND u.member_id IS NOT NULL AND m.id IS NULL;

-- 3. Members with MORE THAN ONE member-role login (should be impossible
--    under the partial unique index from the Controlled Remediation
--    pass, but check pre-existing data from before that index was
--    added).
SELECT member_id, count(*) AS n
FROM users
WHERE role = 'member' AND member_id IS NOT NULL
GROUP BY member_id
HAVING count(*) > 1;

-- 4. Spot-check a specific member (replace the PSN below) -- shows
--    exactly what the fixed Members table endpoint will now compute for
--    them.
-- SELECT m.id, m.psn, m.name,
--        u.id AS login_user_id, u.account_status AS login_account_status
-- FROM members m
-- LEFT JOIN users u ON u.member_id = m.id AND u.role = 'member'
-- WHERE m.psn = '32074';
