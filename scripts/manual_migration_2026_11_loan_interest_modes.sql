-- Loan interest deduction modes and separately-paid loan fees (2026-11).
--
-- Four additive changes:
--
-- 1. interestdeductionmode: how (and whether) interest is taken from the
--    disbursed amount or spread across the term. `at_source` reproduces
--    today's behaviour -- interest is withheld from the payout but the
--    member still repays the full principal-plus-interest figure.
--    `spread_over_tenure` and `spread_first_months` pay out the full
--    principal and collect interest through the instalments.
--
-- 2. The mode is resolved like the interest RATE: a rate version may
--    override the loan type, which may override the cooperative default.
--    Each of those three places therefore gets nullable
--    interest_mode / interest_spread_months, with the cooperative default
--    non-null and backfilled to at_source so no existing behaviour moves.
--
-- 3. loans snapshots the resolved mode (interest_mode,
--    interest_spread_months, interest_installment) because one
--    monthly_installment alone cannot describe the months where extra
--    interest is collected. Existing loans are backfilled to at_source
--    with interest_installment 0 -- their stored figures are left exactly
--    as they were.
--
-- 4. loan_fee_payments: the loan type's processing fee is paid
--    SEPARATELY; it is NOT deducted from the loan, NOT added to
--    total_repayable and NOT part of any instalment. loans.fee_amount
--    records what is owed (snapshot of flat_charge at disbursement) and
--    this table is the verified proof ledger -- cooperative income for a
--    future cashbook to report.
--
-- IDEMPOTENT: every object is created only when missing, so re-running
-- the file is a no-op, and it is a no-op where create_all() has already
-- built the table from the current models (columns still need this file
-- on databases created before the change).

DO $$
BEGIN
    CREATE TYPE interestdeductionmode AS ENUM (
        'at_source', 'spread_over_tenure', 'spread_first_months'
    );
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

DO $$
BEGIN
    CREATE TYPE feepaymentstatus AS ENUM (
        'awaiting_verification', 'verified', 'rejected'
    );
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

-- Cooperative-wide default, used when neither the rate version nor the
-- loan type names a mode.
ALTER TABLE settings
    ADD COLUMN IF NOT EXISTS loan_interest_mode interestdeductionmode NOT NULL DEFAULT 'at_source',
    ADD COLUMN IF NOT EXISTS loan_interest_spread_months INTEGER;

-- Loan type's current (cached) terms; NULL means "inherit".
ALTER TABLE loan_types
    ADD COLUMN IF NOT EXISTS interest_mode interestdeductionmode,
    ADD COLUMN IF NOT EXISTS interest_spread_months INTEGER;

-- Effective-dated terms: the same nullable-inherits rule as the rate.
ALTER TABLE loan_type_rate_versions
    ADD COLUMN IF NOT EXISTS interest_mode interestdeductionmode,
    ADD COLUMN IF NOT EXISTS interest_spread_months INTEGER;

-- Disbursed loans snapshot the resolved mode so payroll arrears are
-- computed with the rules agreed at disbursement, not today's settings.
ALTER TABLE loans
    ADD COLUMN IF NOT EXISTS interest_mode interestdeductionmode NOT NULL DEFAULT 'at_source',
    ADD COLUMN IF NOT EXISTS interest_spread_months INTEGER,
    ADD COLUMN IF NOT EXISTS interest_installment NUMERIC(14, 2) NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS fee_amount NUMERIC(14, 2) NOT NULL DEFAULT 0;

DO $$
BEGIN
    ALTER TABLE loans
        ADD CONSTRAINT ck_loans_interest_installment_nonnegative
        CHECK (interest_installment >= 0);
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

DO $$
BEGIN
    ALTER TABLE loans
        ADD CONSTRAINT ck_loans_fee_amount_nonnegative
        CHECK (fee_amount >= 0);
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

DO $$
BEGIN
    ALTER TABLE settings
        ADD CONSTRAINT ck_settings_loan_interest_spread_months_positive
        CHECK (loan_interest_spread_months IS NULL OR loan_interest_spread_months > 0);
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

CREATE TABLE IF NOT EXISTS loan_fee_payments (
    id UUID NOT NULL PRIMARY KEY,
    loan_id UUID NOT NULL REFERENCES loans(id) ON DELETE CASCADE,
    member_id UUID NOT NULL REFERENCES members(id) ON DELETE CASCADE,
    amount NUMERIC(14, 2) NOT NULL,
    payment_reference VARCHAR NOT NULL,
    receipt_image_base64 TEXT NOT NULL,
    receipt_content_type VARCHAR NOT NULL,
    status feepaymentstatus NOT NULL DEFAULT 'awaiting_verification',
    rejection_reason VARCHAR,
    verified_by_user_id UUID REFERENCES users(id),
    verified_at TIMESTAMP WITHOUT TIME ZONE,
    created_at TIMESTAMP WITHOUT TIME ZONE,
    updated_at TIMESTAMP WITHOUT TIME ZONE
);

-- The review queue asks for "payments with this status, oldest first".
CREATE INDEX IF NOT EXISTS ix_loan_fee_payments_status
    ON loan_fee_payments (status);

CREATE INDEX IF NOT EXISTS ix_loan_fee_payments_loan_id
    ON loan_fee_payments (loan_id);

CREATE INDEX IF NOT EXISTS ix_loan_fee_payments_member_id
    ON loan_fee_payments (member_id);
