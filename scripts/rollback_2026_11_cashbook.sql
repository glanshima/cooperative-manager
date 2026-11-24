-- Rollback for manual_migration_2026_11_cashbook.sql.
--
-- Reverses only what the migration added. The deployed code also runs
-- Base.metadata.create_all() on boot, which may have created the three
-- cashbook tables before this file ran; they are dropped here either way.
--
-- Destructive: every posted journal entry and every recorded payout method
-- is deleted. Run only to abandon the cashbook deploy, before officers
-- post the opening journal. The named restore point taken before the
-- migration (Neon branch pre-cashbook-2026-11-24) is the recovery path if
-- data must be kept.

DROP TABLE IF EXISTS cashbook_lines;
DROP TABLE IF EXISTS cashbook_period_locks;
DROP TABLE IF EXISTS cashbook_entries;
DROP TABLE IF EXISTS cashbook_accounts;

ALTER TABLE member_settlements
    DROP COLUMN IF EXISTS paid_from;

DROP TYPE IF EXISTS settlementpaymentmethod;
DROP TYPE IF EXISTS cashbookentrysource;
DROP TYPE IF EXISTS cashbookaccountkind;
