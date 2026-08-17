-- Run this once in Neon's SQL Editor before redeploying the backend.
-- Round 2 of the "flagged items" batch.

-- Loans: split the single disbursement_account_number into a structured
-- set (bank name, account name, account number). Existing rows already
-- have disbursement_account_number populated from Round 1's migration;
-- we keep that column and just add the two new ones alongside it.
ALTER TABLE loans
    ADD COLUMN IF NOT EXISTS disbursement_bank_name VARCHAR;
ALTER TABLE loans
    ADD COLUMN IF NOT EXISTS disbursement_account_name VARCHAR;

-- Loan applications: structured alternate account (replacing the old
-- single alternate_account_number -- kept as-is, just adding the two
-- new fields alongside it; any existing rows with only
-- alternate_account_number set will simply have blank bank/account name,
-- which is fine for historical data).
ALTER TABLE loan_applications
    ADD COLUMN IF NOT EXISTS alternate_bank_name VARCHAR;
ALTER TABLE loan_applications
    ADD COLUMN IF NOT EXISTS alternate_account_name VARCHAR;

-- Loan applications: cancellation support
ALTER TABLE loan_applications
    ADD COLUMN IF NOT EXISTS cancelled_at TIMESTAMP;

-- Loan applications: reapply support
ALTER TABLE loan_applications
    ADD COLUMN IF NOT EXISTS can_reapply BOOLEAN NOT NULL DEFAULT true;
ALTER TABLE loan_applications
    ADD COLUMN IF NOT EXISTS reapplied_from_id UUID REFERENCES loan_applications(id);

-- The loan_applications.status enum needs a new 'cancelled' value.
-- Postgres requires this to be added explicitly to the existing enum type.
-- Find your enum type's name first if this doesn't match:
--   SELECT typname FROM pg_type WHERE typname LIKE '%loanapplicationstatus%';
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_enum
        WHERE enumlabel = 'cancelled'
        AND enumtypid = (SELECT oid FROM pg_type WHERE typname = 'loanapplicationstatus')
    ) THEN
        ALTER TYPE loanapplicationstatus ADD VALUE 'cancelled';
    END IF;
END$$;
