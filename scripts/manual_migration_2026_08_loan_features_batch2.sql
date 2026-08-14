-- Run this once in Neon's SQL Editor before redeploying the backend.
--
-- As before: create_all() creates any brand-new tables automatically
-- (loan_type_rate_versions, loan_repayments), but does NOT add columns
-- to tables that already exist with data (members, loan_types, loans,
-- loan_applications). Run this manually first.

-- Members: next of kin expansion
ALTER TABLE members
    ADD COLUMN IF NOT EXISTS next_of_kin_address VARCHAR;
ALTER TABLE members
    ADD COLUMN IF NOT EXISTS next_of_kin_email VARCHAR;
ALTER TABLE members
    ADD COLUMN IF NOT EXISTS next_of_kin_relationship VARCHAR;

-- Loans: interest-at-source model needs net_disbursed, plus a snapshot
-- of which account the money went to
ALTER TABLE loans
    ADD COLUMN IF NOT EXISTS net_disbursed NUMERIC(14, 2);
ALTER TABLE loans
    ADD COLUMN IF NOT EXISTS disbursement_account_number VARCHAR;

-- Backfill any existing loan rows (e.g. the test Capital Loan disbursed
-- before this change) that were computed under the OLD add-on-interest
-- formula. Their actual disbursement already happened under that old
-- assumption, so the closest honest value for what they actually
-- received is just the principal (interest wasn't deducted at source for
-- these -- it was already added into what they owe back). This is a
-- one-time correction for historical rows only; every loan disbursed
-- from now on computes net_disbursed correctly at creation time.
UPDATE loans SET net_disbursed = principal WHERE net_disbursed IS NULL;

-- Now that every row has a value, make it required going forward
ALTER TABLE loans
    ALTER COLUMN net_disbursed SET NOT NULL;

-- Loan applications: tenure negotiation + disbursement preferences
ALTER TABLE loan_applications
    ADD COLUMN IF NOT EXISTS requested_tenure_months INTEGER;
ALTER TABLE loan_applications
    ADD COLUMN IF NOT EXISTS approved_tenure_months INTEGER;
ALTER TABLE loan_applications
    ADD COLUMN IF NOT EXISTS tenure_decision_reason VARCHAR;
ALTER TABLE loan_applications
    ADD COLUMN IF NOT EXISTS preferred_disbursement_date DATE;
ALTER TABLE loan_applications
    ADD COLUMN IF NOT EXISTS use_default_account BOOLEAN NOT NULL DEFAULT true;
ALTER TABLE loan_applications
    ADD COLUMN IF NOT EXISTS alternate_account_number VARCHAR;

-- Nothing else to do -- loan_type_rate_versions and loan_repayments are
-- brand new tables and will be created automatically by create_all() the
-- moment the new backend code deploys and starts up.
