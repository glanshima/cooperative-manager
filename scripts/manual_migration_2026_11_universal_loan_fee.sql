-- One universal loan/application fee and frozen approval terms (2026-11).
--
-- Settings.loan_form_fee is the sole fee amount for new loans. The existing
-- LoanApplication.form_fee_amount snapshot remains the canonical amount paid
-- during self-service application. Per-type flat_charge values and historical
-- LoanFeePayment rows are retained unchanged for audit and reconciliation.
--
-- Approval stores the interest terms that were effective when the decision was
-- made. Disbursement uses those stored terms instead of repricing the loan.
-- Legacy approved applications predate these columns and keep the old fallback
-- to the terms effective at disbursement.

ALTER TABLE loan_applications
    ADD COLUMN IF NOT EXISTS approved_interest_rate NUMERIC(6, 4),
    ADD COLUMN IF NOT EXISTS approved_interest_mode interestdeductionmode,
    ADD COLUMN IF NOT EXISTS approved_interest_spread_months INTEGER;

ALTER TABLE loans
    ADD COLUMN IF NOT EXISTS fee_paid_via_application BOOLEAN NOT NULL DEFAULT false;

UPDATE loans
SET fee_paid_via_application = true
WHERE id IN (
    SELECT resulting_loan_id
    FROM loan_applications
    WHERE resulting_loan_id IS NOT NULL
);

DO $$
BEGIN
    ALTER TABLE loan_applications
        ADD CONSTRAINT ck_loan_applications_approved_interest_rate_nonnegative
        CHECK (approved_interest_rate IS NULL OR approved_interest_rate >= 0);
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

DO $$
BEGIN
    ALTER TABLE loan_applications
        ADD CONSTRAINT ck_loan_applications_approved_interest_spread_months_positive
        CHECK (approved_interest_spread_months IS NULL OR approved_interest_spread_months > 0);
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

-- A loan owes one fee, so it can have only one pending or verified fee
-- payment. A trigger rather than a partial unique index preserves any
-- duplicate historical rows instead of making this migration fail or
-- rewriting audit history. The loan-row lock also serializes writers that
-- do not go through the API's own transaction lock.
CREATE OR REPLACE FUNCTION enforce_single_loan_fee_obligation()
RETURNS TRIGGER AS $$
DECLARE
    should_enforce BOOLEAN;
BEGIN
    should_enforce := NEW.status::text IN ('awaiting_verification', 'verified');
    IF TG_OP = 'UPDATE' THEN
        should_enforce := should_enforce
            AND (NEW.status IS DISTINCT FROM OLD.status OR NEW.loan_id IS DISTINCT FROM OLD.loan_id);
    END IF;

    IF should_enforce THEN
        PERFORM 1 FROM loans WHERE id = NEW.loan_id FOR UPDATE;

        IF EXISTS (
            SELECT 1
            FROM loan_fee_payments
            WHERE loan_id = NEW.loan_id
                AND id IS DISTINCT FROM NEW.id
                AND status::text IN ('awaiting_verification', 'verified')
        ) THEN
            RAISE EXCEPTION 'A loan can have only one pending or verified fee payment'
                USING ERRCODE = '23505';
        END IF;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_enforce_single_loan_fee_obligation ON loan_fee_payments;
CREATE TRIGGER trg_enforce_single_loan_fee_obligation
BEFORE INSERT OR UPDATE ON loan_fee_payments
FOR EACH ROW EXECUTE FUNCTION enforce_single_loan_fee_obligation();
