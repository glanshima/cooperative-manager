-- MACT Cooperative Manager -- Phase 1 remediation: database-level
-- integrity constraints (Section 6 of the remediation prompt).
--
-- PHASE1_IMPLEMENTATION_REPORT.md (Section H, item 6) originally deferred
-- DB-level CHECK constraints on financial amounts to Phase 2, reasoning
-- that Pydantic-level validation + row locking were sufficient for Phase
-- 1. On review, a defense-in-depth DB constraint costs very little to add
-- now and closes the gap where a value could reach these columns through
-- any path OTHER than the validated API (a future script, a manual SQL
-- fix, an admin tool, a bug in a not-yet-written Phase 2+ endpoint) --
-- exactly the kind of protection Section 15/16 (financial history /
-- database integrity) asks for. This migration adds that layer.
--
-- SAFE-MIGRATION PROCEDURE (per Section 6's instruction to check
-- existing-data assumptions before adding constraints that could reject
-- rows already present):
--   1. Run the SELECT queries in Part 1 below FIRST, by hand, and confirm
--      each returns zero rows. The project is still in a testing-only
--      phase (no live cooperative data yet per current project state),
--      so these are expected to return zero, but do not skip checking --
--      that expectation is exactly what this step verifies rather than
--      assumes.
--   2. If any query returns rows, fix or remove that data before
--      proceeding -- do NOT relax a constraint below to accommodate bad
--      data; that defeats the purpose of adding it.
--   3. Only after confirming zero violations, run Part 2 (the ALTER TABLE
--      ... ADD CONSTRAINT statements). They are written as plain (not
--      NOT VALID) constraints since Part 1 already established there is
--      nothing for Postgres to validate against on this pass; if this
--      migration is ever run against a database that already has rows,
--      re-run Part 1 first regardless of this comment.
--
-- Rollback: each constraint below has a matching `ALTER TABLE ... DROP
-- CONSTRAINT` that would need to be run manually if ever required; none
-- is included by default, matching the convention set by the Phase 1
-- security-foundation migration.

-- ---------------------------------------------------------------------
-- Part 1 -- pre-flight checks. Run these first; every query should
-- return 0 rows before proceeding to Part 2.
-- ---------------------------------------------------------------------
-- SELECT count(*) FROM loans WHERE principal <= 0 OR interest_amount < 0
--        OR net_disbursed < 0 OR total_repayable <= 0
--        OR monthly_installment <= 0 OR amount_repaid < 0;
-- SELECT count(*) FROM loan_applications WHERE requested_amount <= 0
--        OR (approved_amount IS NOT NULL AND approved_amount <= 0)
--        OR form_fee_amount < 0;
-- SELECT count(*) FROM loan_repayments WHERE amount_claimed <= 0;
-- SELECT count(*) FROM loan_types WHERE interest_rate < 0 OR tenure_months <= 0
--        OR flat_charge < 0;
-- SELECT count(*) FROM loan_type_rate_versions WHERE interest_rate < 0
--        OR tenure_months <= 0 OR flat_charge < 0;
-- SELECT count(*) FROM settings WHERE loan_form_fee < 0;
-- SELECT count(*) FROM users WHERE failed_login_count < 0;

-- ---------------------------------------------------------------------
-- Part 2 -- constraints
-- ---------------------------------------------------------------------

ALTER TABLE loans
    ADD CONSTRAINT ck_loans_principal_positive CHECK (principal > 0),
    ADD CONSTRAINT ck_loans_interest_amount_nonnegative CHECK (interest_amount >= 0),
    ADD CONSTRAINT ck_loans_net_disbursed_nonnegative CHECK (net_disbursed >= 0),
    ADD CONSTRAINT ck_loans_total_repayable_positive CHECK (total_repayable > 0),
    ADD CONSTRAINT ck_loans_monthly_installment_positive CHECK (monthly_installment > 0),
    ADD CONSTRAINT ck_loans_amount_repaid_nonnegative CHECK (amount_repaid >= 0);

ALTER TABLE loan_applications
    ADD CONSTRAINT ck_loan_applications_requested_amount_positive CHECK (requested_amount > 0),
    ADD CONSTRAINT ck_loan_applications_approved_amount_positive
        CHECK (approved_amount IS NULL OR approved_amount > 0),
    ADD CONSTRAINT ck_loan_applications_form_fee_nonnegative CHECK (form_fee_amount >= 0);

ALTER TABLE loan_repayments
    ADD CONSTRAINT ck_loan_repayments_amount_claimed_positive CHECK (amount_claimed > 0);

ALTER TABLE loan_types
    ADD CONSTRAINT ck_loan_types_interest_rate_nonnegative CHECK (interest_rate >= 0),
    ADD CONSTRAINT ck_loan_types_tenure_months_positive CHECK (tenure_months > 0),
    ADD CONSTRAINT ck_loan_types_flat_charge_nonnegative CHECK (flat_charge >= 0);

ALTER TABLE loan_type_rate_versions
    ADD CONSTRAINT ck_loan_type_rate_versions_interest_rate_nonnegative CHECK (interest_rate >= 0),
    ADD CONSTRAINT ck_loan_type_rate_versions_tenure_months_positive CHECK (tenure_months > 0),
    ADD CONSTRAINT ck_loan_type_rate_versions_flat_charge_nonnegative CHECK (flat_charge >= 0);

ALTER TABLE settings
    ADD CONSTRAINT ck_settings_loan_form_fee_nonnegative CHECK (loan_form_fee >= 0);

ALTER TABLE users
    ADD CONSTRAINT ck_users_failed_login_count_nonnegative CHECK (failed_login_count >= 0);

-- ---------------------------------------------------------------------
-- Part 3 -- post-migration verification
-- ---------------------------------------------------------------------
-- SELECT conname, conrelid::regclass FROM pg_constraint
--        WHERE conname LIKE 'ck_%' ORDER BY conname;   -- expect 13 rows
