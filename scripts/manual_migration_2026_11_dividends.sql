-- Dividends: appropriating a closed year's surplus (2026-11).
--
-- A dividend is not an expense. It is a distribution of surplus that has
-- already been earned, so this migration adds the minimum the cashbook
-- needs to record it properly:
--
-- 1. Settings. The policy lives at cooperative level (basis, pool mode,
--    reserve/honorarium/payout split, rounding, withholding, eligibility)
--    rather than in literals on a spreadsheet.
--
-- 2. dividend_runs -- one immutable declaration per fiscal year. The
--    run snapshots the surplus window, the rates and the pool so a later
--    settings change can never rewrite a declared dividend.
--
-- 3. dividend_allocations -- each eligible member's basis, share, gross,
--    withholding and net, with the rounding adjustment shown rather than
--    buried, because the allocations must add up to the pool exactly.
--
-- 4. dividend_payouts -- one row per payment batch (cash or bank), which
--    is what the cashbook entry is keyed to. Allocations point at the
--    batch that paid them.
--
-- The cashbook gains three entry sources and three system accounts:
-- dividends and honorarium are equities becoming liabilities at
-- declaration, then liabilities becoming cash at payment.
--
-- Re-running the file is safe: every object is guarded.

DO $$
BEGIN
    ALTER TYPE cashbookentrysource ADD VALUE IF NOT EXISTS 'year_close';
    ALTER TYPE cashbookentrysource ADD VALUE IF NOT EXISTS 'dividend_declaration';
    ALTER TYPE cashbookentrysource ADD VALUE IF NOT EXISTS 'dividend_payment';
EXCEPTION
    WHEN undefined_object THEN NULL;
END $$;

DO $$
BEGIN
    CREATE TYPE dividendbasis AS ENUM (
        'none',
        'net_savings_closing',
        'net_savings_average',
        'declared_rate_on_savings',
        'share_capital',
        'patronage',
        'equal',
        'hybrid'
    );
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

DO $$
BEGIN
    CREATE TYPE dividendpoolmode AS ENUM ('net_income_share', 'savings_percent', 'fixed_amount');
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

DO $$
BEGIN
    CREATE TYPE dividendrunstatus AS ENUM ('draft', 'declared', 'paid');
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

DO $$
BEGIN
    CREATE TYPE dividendrounding AS ENUM ('two_dp', 'whole_currency');
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

DO $$
BEGIN
    CREATE TYPE dividendpayoutmethod AS ENUM ('cash', 'bank');
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

DO $$
BEGIN
    CREATE TYPE dividendpaymentpolicy AS ENUM ('bank', 'cash', 'either');
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

-- ---------------------------------------------------------------------------
-- Settings
-- ---------------------------------------------------------------------------

ALTER TABLE settings
    ADD COLUMN IF NOT EXISTS fiscal_year_start_month INTEGER NOT NULL DEFAULT 1,
    ADD COLUMN IF NOT EXISTS dividend_basis dividendbasis NOT NULL DEFAULT 'none',
    ADD COLUMN IF NOT EXISTS dividend_pool_mode dividendpoolmode NOT NULL DEFAULT 'net_income_share',
    ADD COLUMN IF NOT EXISTS dividend_reserve_pct NUMERIC(5, 2) NOT NULL DEFAULT 4.70,
    ADD COLUMN IF NOT EXISTS dividend_honorarium_pct NUMERIC(5, 2) NOT NULL DEFAULT 3.00,
    ADD COLUMN IF NOT EXISTS dividend_payout_pct NUMERIC(5, 2) NOT NULL DEFAULT 92.30,
    ADD COLUMN IF NOT EXISTS dividend_declared_rate_pct NUMERIC(5, 2),
    ADD COLUMN IF NOT EXISTS dividend_fixed_pool_amount NUMERIC(14, 2),
    ADD COLUMN IF NOT EXISTS dividend_hybrid_savings_pct NUMERIC(5, 2) NOT NULL DEFAULT 50.00,
    ADD COLUMN IF NOT EXISTS dividend_min_membership_months INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS dividend_include_exited BOOLEAN NOT NULL DEFAULT false,
    ADD COLUMN IF NOT EXISTS dividend_rounding dividendrounding NOT NULL DEFAULT 'two_dp',
    ADD COLUMN IF NOT EXISTS dividend_withholding_pct NUMERIC(5, 2) NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS dividend_payment_method dividendpaymentpolicy NOT NULL DEFAULT 'bank';

DO $$
BEGIN
    ALTER TABLE settings
        ADD CONSTRAINT ck_settings_fiscal_year_start_month
        CHECK (fiscal_year_start_month BETWEEN 1 AND 12);
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

DO $$
BEGIN
    ALTER TABLE settings
        ADD CONSTRAINT ck_settings_dividend_pct_ranges
        CHECK (
            dividend_reserve_pct BETWEEN 0 AND 100
            AND dividend_honorarium_pct BETWEEN 0 AND 100
            AND dividend_payout_pct BETWEEN 0 AND 100
            AND dividend_hybrid_savings_pct BETWEEN 0 AND 100
            AND dividend_withholding_pct BETWEEN 0 AND 100
        );
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

DO $$
BEGIN
    ALTER TABLE settings
        ADD CONSTRAINT ck_settings_dividend_min_months
        CHECK (dividend_min_membership_months >= 0);
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

-- ---------------------------------------------------------------------------
-- Runs, allocations and payment batches
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS dividend_runs (
    id UUID PRIMARY KEY,
    fiscal_year INTEGER NOT NULL UNIQUE,
    period_start DATE NOT NULL,
    period_end DATE NOT NULL,
    status dividendrunstatus NOT NULL DEFAULT 'draft',
    basis dividendbasis NOT NULL,
    pool_mode dividendpoolmode NOT NULL,

    -- Snapshot of the policy and the surplus window at computation time.
    surplus NUMERIC(14, 2) NOT NULL DEFAULT 0,
    reserve_pct NUMERIC(5, 2) NOT NULL DEFAULT 0,
    reserve_amount NUMERIC(14, 2) NOT NULL DEFAULT 0,
    honorarium_pct NUMERIC(5, 2) NOT NULL DEFAULT 0,
    honorarium_amount NUMERIC(14, 2) NOT NULL DEFAULT 0,
    payout_pct NUMERIC(5, 2) NOT NULL DEFAULT 0,
    pool_amount NUMERIC(14, 2) NOT NULL DEFAULT 0,
    declared_rate_pct NUMERIC(5, 2),
    fixed_pool_amount NUMERIC(14, 2),
    hybrid_savings_pct NUMERIC(5, 2) NOT NULL DEFAULT 50,
    withholding_pct NUMERIC(5, 2) NOT NULL DEFAULT 0,
    rounding dividendrounding NOT NULL DEFAULT 'two_dp',
    min_membership_months INTEGER NOT NULL DEFAULT 0,
    include_exited BOOLEAN NOT NULL DEFAULT false,

    -- Snapshot of what was actually posted and allocated.
    closed_income_total NUMERIC(14, 2) NOT NULL DEFAULT 0,
    closed_expense_total NUMERIC(14, 2) NOT NULL DEFAULT 0,
    total_basis_amount NUMERIC(18, 6) NOT NULL DEFAULT 0,
    total_gross NUMERIC(14, 2) NOT NULL DEFAULT 0,
    total_withholding NUMERIC(14, 2) NOT NULL DEFAULT 0,
    total_net NUMERIC(14, 2) NOT NULL DEFAULT 0,
    rounding_residual NUMERIC(14, 2) NOT NULL DEFAULT 0,
    eligible_member_count INTEGER NOT NULL DEFAULT 0,

    note TEXT,
    declared_on DATE,
    declared_by_user_id UUID REFERENCES users(id),
    created_by_user_id UUID REFERENCES users(id),
    created_at TIMESTAMP,
    updated_at TIMESTAMP,

    CONSTRAINT ck_dividend_runs_no_self_period CHECK (period_start <= period_end)
);

CREATE TABLE IF NOT EXISTS dividend_payouts (
    id UUID PRIMARY KEY,
    run_id UUID NOT NULL REFERENCES dividend_runs(id) ON DELETE CASCADE,
    paid_on DATE NOT NULL,
    method dividendpayoutmethod NOT NULL,
    reference VARCHAR(64) NOT NULL,
    amount NUMERIC(14, 2) NOT NULL,
    note TEXT,
    created_by_user_id UUID REFERENCES users(id),
    created_at TIMESTAMP,
    CONSTRAINT ck_dividend_payouts_amount_positive CHECK (amount > 0)
);

CREATE TABLE IF NOT EXISTS dividend_allocations (
    id UUID PRIMARY KEY,
    run_id UUID NOT NULL REFERENCES dividend_runs(id) ON DELETE CASCADE,
    member_id UUID NOT NULL REFERENCES members(id) ON DELETE CASCADE,
    basis_amount NUMERIC(18, 6) NOT NULL DEFAULT 0,
    share_ratio NUMERIC(18, 12) NOT NULL DEFAULT 0,
    gross_amount NUMERIC(14, 2) NOT NULL DEFAULT 0,
    withholding_amount NUMERIC(14, 2) NOT NULL DEFAULT 0,
    net_amount NUMERIC(14, 2) NOT NULL DEFAULT 0,
    rounding_adjustment NUMERIC(14, 2) NOT NULL DEFAULT 0,
    payout_id UUID REFERENCES dividend_payouts(id) ON DELETE SET NULL,
    created_at TIMESTAMP,
    CONSTRAINT uq_dividend_allocations_member UNIQUE (run_id, member_id),
    CONSTRAINT ck_dividend_allocations_amounts_nonnegative CHECK (
        basis_amount >= 0
        AND gross_amount >= 0
        AND withholding_amount >= 0
        AND net_amount >= 0
    )
);

CREATE INDEX IF NOT EXISTS ix_dividend_payouts_run_id ON dividend_payouts (run_id);
CREATE INDEX IF NOT EXISTS ix_dividend_allocations_run_id ON dividend_allocations (run_id);
CREATE INDEX IF NOT EXISTS ix_dividend_allocations_member_id ON dividend_allocations (member_id);
CREATE INDEX IF NOT EXISTS ix_dividend_allocations_payout_id ON dividend_allocations (payout_id);

-- ---------------------------------------------------------------------------
-- Chart of accounts
-- ---------------------------------------------------------------------------

INSERT INTO cashbook_accounts (id, code, name, kind, system_key, is_active, created_at)
VALUES
    (gen_random_uuid(), '2030', 'Dividends payable', 'liability', 'DIVIDENDS_PAYABLE', true, now()),
    (gen_random_uuid(), '2040', 'Honorarium payable', 'liability', 'HONORARIUM_PAYABLE', true, now()),
    (gen_random_uuid(), '2050', 'Withholding tax payable', 'liability', 'WITHHOLDING_PAYABLE', true, now())
ON CONFLICT DO NOTHING;

-- The starter chart already carried a Reserve equity account; the
-- appropriation has to name it, so it becomes a system account.
UPDATE cashbook_accounts
SET system_key = 'RESERVE'
WHERE code = '3010'
  AND system_key IS NULL;
