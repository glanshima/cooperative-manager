-- Payroll deductions module (2026-11).
--
-- Creates the monthly deduction ledger that replaces the workbook's 59
-- per-month deduction tables: one payroll_deductions row per member per
-- month, with payroll_deduction_lines for the monthly contribution, the
-- explicit loan allocation, and any other requested deduction.
--
-- Idempotent: safe to re-run, and a no-op on a database where
-- Base.metadata.create_all() has already created these tables from the
-- current models.

DO $$
BEGIN
    CREATE TYPE payrolldeductionstatus AS ENUM (
        'draft', 'submitted', 'confirmed', 'not_deducted', 'void'
    );
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

DO $$
BEGIN
    CREATE TYPE payrolldeductionlinecategory AS ENUM (
        'monthly_contribution', 'loan_repayment', 'other'
    );
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

CREATE TABLE IF NOT EXISTS payroll_deductions (
    id UUID NOT NULL PRIMARY KEY,
    member_id UUID NOT NULL REFERENCES members(id) ON DELETE CASCADE,
    deduction_month DATE NOT NULL,
    payroll_reference VARCHAR,
    note TEXT,
    status payrolldeductionstatus NOT NULL DEFAULT 'draft',
    created_by_user_id UUID REFERENCES users(id),
    submitted_by_user_id UUID REFERENCES users(id),
    submitted_at TIMESTAMP WITHOUT TIME ZONE,
    confirmed_by_user_id UUID REFERENCES users(id),
    confirmed_at TIMESTAMP WITHOUT TIME ZONE,
    not_deducted_by_user_id UUID REFERENCES users(id),
    not_deducted_at TIMESTAMP WITHOUT TIME ZONE,
    not_deducted_reason TEXT,
    returned_at TIMESTAMP WITHOUT TIME ZONE,
    return_reason TEXT,
    voided_by_user_id UUID REFERENCES users(id),
    voided_at TIMESTAMP WITHOUT TIME ZONE,
    void_reason TEXT,
    created_at TIMESTAMP WITHOUT TIME ZONE,
    updated_at TIMESTAMP WITHOUT TIME ZONE
);

CREATE TABLE IF NOT EXISTS payroll_deduction_lines (
    id UUID NOT NULL PRIMARY KEY,
    deduction_id UUID NOT NULL REFERENCES payroll_deductions(id) ON DELETE CASCADE,
    category payrolldeductionlinecategory NOT NULL,
    loan_id UUID REFERENCES loans(id),
    label VARCHAR,
    amount NUMERIC(14, 2) NOT NULL,
    created_at TIMESTAMP WITHOUT TIME ZONE,
    CONSTRAINT ck_payroll_deduction_lines_amount_positive CHECK (amount > 0),
    CONSTRAINT ck_payroll_deduction_lines_loan_link CHECK (
        (category = 'loan_repayment' AND loan_id IS NOT NULL)
        OR (category <> 'loan_repayment' AND loan_id IS NULL)
    )
);

-- One live (non-void) record per member per month; voided records stay as
-- history without blocking a correction.
CREATE UNIQUE INDEX IF NOT EXISTS uq_payroll_deductions_member_month_active
    ON payroll_deductions (member_id, deduction_month)
    WHERE status <> 'void';

CREATE INDEX IF NOT EXISTS ix_payroll_deductions_deduction_month
    ON payroll_deductions (deduction_month);
