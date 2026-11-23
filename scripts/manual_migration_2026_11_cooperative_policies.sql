-- Cooperative-level contribution and loan-default policy (2026-11).
--
-- Five settings, all on the single-row `settings` table (one database per
-- cooperative, so the row IS the cooperative):
--
-- 1. minimum_monthly_contribution -- the floor a member's agreed monthly
--    contribution must meet. Previously hardcoded in validation.py; the
--    floor now belongs to the cooperative and changes without a deploy.
--    Existing deployments are backfilled to 5000 so no current behaviour
--    moves, then the column default is reset to 0 ("no floor") -- a
--    database that never ran this file keeps its old, more restrictive
--    behaviour, which is the safe direction.
--
-- 2. default_monthly_contribution -- what a new member form pre-fills.
--    Also backfilled to the old 5000 figure, then defaulted to 0.
--
-- 3. loan_default_charge_pct -- the charge raised on a member who misses
--    an instalment. Charged ONCE per missed instalment, never compounded,
--    and never taken out of savings: it is income to the cooperative.
--    0 means no charge (the default for a fresh cooperative).
--
-- 4. loan_default_grace_mode / loan_default_grace_days -- when a missed
--    instalment BECOMES a default. `next_payroll` is the staff-cooperative
--    rule: the member keeps the whole instalment month, and the shortfall
--    defaults only when the next payroll deduction is processed. `days` is
--    a fixed window counted from the close of the instalment month;
--    grace_days is only meaningful in that mode and is 0..365.
--
-- IDEMPOTENT: enum and columns are created only when missing, the backfill
-- only touches rows that are still NULL, and the constraint blocks tolerate
-- duplicate_object. On a database whose tables were built by create_all()
-- from the current models the ADD COLUMN statements are no-ops and the
-- backfill finds nothing to do.

DO $$
BEGIN
    CREATE TYPE loandefaultgracemode AS ENUM ('next_payroll', 'days');
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

ALTER TABLE settings
    ADD COLUMN IF NOT EXISTS minimum_monthly_contribution NUMERIC(14, 2),
    ADD COLUMN IF NOT EXISTS default_monthly_contribution NUMERIC(14, 2),
    ADD COLUMN IF NOT EXISTS loan_default_charge_pct NUMERIC(5, 2),
    ADD COLUMN IF NOT EXISTS loan_default_grace_mode loandefaultgracemode,
    ADD COLUMN IF NOT EXISTS loan_default_grace_days INTEGER;

-- Preserve the pre-migration behaviour on databases that already hold a
-- settings row: the floor and the form default were 5000 in code.
UPDATE settings
SET minimum_monthly_contribution = 5000
WHERE minimum_monthly_contribution IS NULL;

UPDATE settings
SET default_monthly_contribution = 5000
WHERE default_monthly_contribution IS NULL;

-- A fresh cooperative starts with no floor, no charge and the
-- staff-cooperative grace rule; the settings screen configures the rest.
UPDATE settings
SET loan_default_charge_pct = 0
WHERE loan_default_charge_pct IS NULL;

UPDATE settings
SET loan_default_grace_mode = 'next_payroll'
WHERE loan_default_grace_mode IS NULL;

UPDATE settings
SET loan_default_grace_days = 0
WHERE loan_default_grace_days IS NULL;

ALTER TABLE settings
    ALTER COLUMN minimum_monthly_contribution SET NOT NULL,
    ALTER COLUMN minimum_monthly_contribution SET DEFAULT 0,
    ALTER COLUMN default_monthly_contribution SET NOT NULL,
    ALTER COLUMN default_monthly_contribution SET DEFAULT 0,
    ALTER COLUMN loan_default_charge_pct SET NOT NULL,
    ALTER COLUMN loan_default_charge_pct SET DEFAULT 0,
    ALTER COLUMN loan_default_grace_mode SET NOT NULL,
    ALTER COLUMN loan_default_grace_mode SET DEFAULT 'next_payroll',
    ALTER COLUMN loan_default_grace_days SET NOT NULL,
    ALTER COLUMN loan_default_grace_days SET DEFAULT 0;

DO $$
BEGIN
    ALTER TABLE settings
        ADD CONSTRAINT ck_settings_minimum_contribution_nonnegative
        CHECK (minimum_monthly_contribution >= 0);
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

DO $$
BEGIN
    ALTER TABLE settings
        ADD CONSTRAINT ck_settings_default_contribution_nonnegative
        CHECK (default_monthly_contribution >= 0);
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

DO $$
BEGIN
    ALTER TABLE settings
        ADD CONSTRAINT ck_settings_loan_default_charge_pct_range
        CHECK (loan_default_charge_pct >= 0 AND loan_default_charge_pct <= 100);
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

DO $$
BEGIN
    ALTER TABLE settings
        ADD CONSTRAINT ck_settings_loan_default_grace_days_range
        CHECK (loan_default_grace_days >= 0 AND loan_default_grace_days <= 365);
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;
