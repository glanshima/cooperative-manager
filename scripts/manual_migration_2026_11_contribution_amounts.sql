-- MACT Cooperative Manager -- monthly contribution amounts (2026-11).
--
-- Four additive changes:
--
-- 1. members.monthly_contribution_amount / contribution_effective_from:
--    the amount payroll deducts as a member's monthly contribution, and
--    the first payroll month it applies to. NULL means "not on file yet"
--    -- every member imported from the spreadsheet starts there, and an
--    officer bootstraps the value once. Later changes go through
--    contribution_change_requests, never a silent edit.
--
-- 2. contribution_change_requests: a member's application to increase or
--    decrease that amount, approved or rejected by an officer holding
--    savings.approve_change / savings.reject_change. Approval sets
--    effective_from to a future month, so confirmed deduction lines keep
--    what was actually deducted and savings history is never rewritten.
--
-- 3. payroll_deduction_lines.expected_amount: what the server computed
--    this line should be (stored contribution, or the loan's monthly
--    installment net of repayments already made that month). NULL means
--    the officer typed the amount themselves. Comparing amount against
--    expected_amount is what makes an override visible in the audit
--    trail and blockable for a conflicted officer.
--
-- 4. loan_repayments.payment_month: the month a repayment was actually
--    paid, so payroll prefill can net it off instead of deducting the
--    same installment twice. Existing rows stay NULL -- the column is
--    deliberately NOT backfilled from verified_at, because a verification
--    date is not a payment date and guessing would corrupt real history.
--
-- The 5000 minimum is enforced in app/validation.py, not as a CHECK here:
-- it is cooperative policy, and duplicating the constant in SQL would let
-- the two drift apart.
--
-- Idempotent: safe to re-run, and a no-op where create_all() has already
-- built these objects from the current models.

ALTER TABLE members
    ADD COLUMN IF NOT EXISTS monthly_contribution_amount NUMERIC(14, 2),
    ADD COLUMN IF NOT EXISTS contribution_effective_from DATE;

DO $$
BEGIN
    CREATE TYPE contributionchangerequeststatus AS ENUM (
        'pending', 'approved', 'rejected'
    );
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

CREATE TABLE IF NOT EXISTS contribution_change_requests (
    id UUID NOT NULL PRIMARY KEY,
    member_id UUID NOT NULL REFERENCES members(id) ON DELETE CASCADE,
    current_amount NUMERIC(14, 2),
    requested_amount NUMERIC(14, 2) NOT NULL,
    reason TEXT,
    status contributionchangerequeststatus NOT NULL DEFAULT 'pending',
    effective_from DATE,
    requested_by_user_id UUID REFERENCES users(id),
    reviewed_by_user_id UUID REFERENCES users(id),
    reviewed_at TIMESTAMP WITHOUT TIME ZONE,
    review_reason TEXT,
    created_at TIMESTAMP WITHOUT TIME ZONE,
    updated_at TIMESTAMP WITHOUT TIME ZONE,
    CONSTRAINT ck_contribution_change_requests_amount_positive CHECK (requested_amount > 0)
);

-- One open application per member: a second request while the first is
-- pending would leave two competing amounts for the same payroll month.
CREATE UNIQUE INDEX IF NOT EXISTS uq_contribution_change_requests_member_pending
    ON contribution_change_requests (member_id)
    WHERE status = 'pending';

CREATE INDEX IF NOT EXISTS ix_contribution_change_requests_member_id
    ON contribution_change_requests (member_id);

CREATE INDEX IF NOT EXISTS ix_contribution_change_requests_status
    ON contribution_change_requests (status);

ALTER TABLE payroll_deduction_lines
    ADD COLUMN IF NOT EXISTS expected_amount NUMERIC(14, 2);

ALTER TABLE loan_repayments
    ADD COLUMN IF NOT EXISTS payment_month DATE;