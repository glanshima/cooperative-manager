-- Loan arrears as an explicit deduction line (2026-11).
--
-- Until now arrears were only annotated beside a loan's instalment line, so
-- a member who had missed months had no way to catch up through payroll: the
-- shortfall was visible and nothing else happened. Arrears become their own
-- line category, which credits Loan.amount_repaid exactly like
-- 'loan_repayment' does (the confirm and void paths key off loan_id, not
-- category) and is kept separate so the printed schedule shows why a month
-- deducts more than one instalment.
--
-- Idempotent: safe to re-run.
--
-- The restated constraint names only the two categories that must NOT carry
-- a loan, instead of naming both loan categories. That is deliberate: ALTER
-- TYPE ... ADD VALUE cannot be followed by any use of the new value in the
-- same transaction, and this runner commits once per file, so 'loan_arrears'
-- must not appear as a literal below.

DO $$
BEGIN
    ALTER TYPE payrolldeductionlinecategory ADD VALUE 'loan_arrears';
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

ALTER TABLE payroll_deduction_lines
    DROP CONSTRAINT IF EXISTS ck_payroll_deduction_lines_loan_link;

ALTER TABLE payroll_deduction_lines
    ADD CONSTRAINT ck_payroll_deduction_lines_loan_link CHECK (
        (category NOT IN ('monthly_contribution', 'other') AND loan_id IS NOT NULL)
        OR (category IN ('monthly_contribution', 'other') AND loan_id IS NULL)
    );
