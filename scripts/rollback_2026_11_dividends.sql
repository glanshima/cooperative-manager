-- Rollback for scripts/manual_migration_2026_11_dividends.sql.
--
-- Run this only if the dividends schema has to be withdrawn before it has
-- posted anything. It removes the module's tables, settings columns and
-- the three payable accounts. Two things deliberately survive:
--
-- * The new cashbook entry-source values ('year_close',
--   'dividend_declaration', 'dividend_payment'). PostgreSQL cannot remove
--   a value from an existing enum without rebuilding the type, and an
--   unused value is harmless.
-- * Reserve (3010) stays a system account. The cashbook's own migration
--   seeded it as an ordinary equity account, but it is a required posting
--   target for any appropriation, so it keeps its key.
--
-- Deleting an account that already carries journal lines will fail on the
-- foreign key. If that happens the module has posted; reverse the entries
-- first rather than deleting the chart rows.

DROP TABLE IF EXISTS dividend_allocations;
DROP TABLE IF EXISTS dividend_payouts;
DROP TABLE IF EXISTS dividend_runs;

ALTER TABLE settings
    DROP COLUMN IF EXISTS fiscal_year_start_month,
    DROP COLUMN IF EXISTS dividend_basis,
    DROP COLUMN IF EXISTS dividend_pool_mode,
    DROP COLUMN IF EXISTS dividend_reserve_pct,
    DROP COLUMN IF EXISTS dividend_honorarium_pct,
    DROP COLUMN IF EXISTS dividend_payout_pct,
    DROP COLUMN IF EXISTS dividend_declared_rate_pct,
    DROP COLUMN IF EXISTS dividend_fixed_pool_amount,
    DROP COLUMN IF EXISTS dividend_hybrid_savings_pct,
    DROP COLUMN IF EXISTS dividend_min_membership_months,
    DROP COLUMN IF EXISTS dividend_include_exited,
    DROP COLUMN IF EXISTS dividend_rounding,
    DROP COLUMN IF EXISTS dividend_withholding_pct,
    DROP COLUMN IF EXISTS dividend_payment_method;

DELETE FROM cashbook_accounts
WHERE system_key IN ('DIVIDENDS_PAYABLE', 'HONORARIUM_PAYABLE', 'WITHHOLDING_PAYABLE')
  AND code IN ('2030', '2040', '2050');
