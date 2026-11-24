-- Cashbook: a double-entry ledger for the cooperative's money.
--
-- The legacy workbook was a single-column cash list where the sign of the
-- amount decided income vs expenditure and member savings sat in the same
-- pot as income. This schema replaces that:
--
-- 1. cashbook_accounts -- the chart of accounts. ``kind`` (asset,
--    liability, equity, income, expense) decides where a balance belongs.
--    ``system_key`` marks the accounts the automatic postings name; those
--    must stay active.
--
-- 2. cashbook_entries / cashbook_lines -- every posting is one balanced
--    journal entry: the sum of debits equals the sum of credits, and each
--    line carries exactly one of the two. Entries are immutable; a
--    correction is a reversing entry that names the original.
--    ``(source, source_id)`` is unique so confirming the same payroll
--    month, repayment or fee twice can never post twice.
--
-- 3. cashbook_period_locks -- a closed month. Nothing may be dated inside
--    it; corrections post in the open month.
--
-- Member settlements gain ``paid_from`` so marking a payout paid says
-- whether the money left the cash box or the bank.
--
-- Re-running the file is safe: every object is guarded and the starter
-- chart is inserted by code.

DO $$
BEGIN
    CREATE TYPE cashbookaccountkind AS ENUM (
        'asset', 'liability', 'equity', 'income', 'expense'
    );
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

DO $$
BEGIN
    CREATE TYPE cashbookentrysource AS ENUM (
        'manual', 'opening', 'reversal', 'payroll_deduction',
        'payroll_deduction_void', 'loan_disbursement', 'loan_repayment',
        'loan_fee', 'settlement', 'settlement_payout'
    );
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

DO $$
BEGIN
    CREATE TYPE settlementpaymentmethod AS ENUM ('cash', 'bank');
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

CREATE TABLE IF NOT EXISTS cashbook_accounts (
    id UUID PRIMARY KEY,
    code VARCHAR(16) NOT NULL UNIQUE,
    name VARCHAR(120) NOT NULL,
    kind cashbookaccountkind NOT NULL,
    system_key VARCHAR(40) UNIQUE,
    is_active BOOLEAN NOT NULL DEFAULT true,
    description TEXT,
    created_at TIMESTAMP,
    updated_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS cashbook_entries (
    id UUID PRIMARY KEY,
    entry_date DATE NOT NULL,
    narration VARCHAR(255) NOT NULL,
    reference VARCHAR(64),
    source cashbookentrysource NOT NULL DEFAULT 'manual',
    source_id UUID,
    reverses_entry_id UUID REFERENCES cashbook_entries(id),
    reversal_reason TEXT,
    posted_by_user_id UUID REFERENCES users(id),
    posted_at TIMESTAMP,
    created_at TIMESTAMP
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_cashbook_entries_source
    ON cashbook_entries (source, source_id)
    WHERE source_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS ix_cashbook_entries_entry_date
    ON cashbook_entries (entry_date);

CREATE TABLE IF NOT EXISTS cashbook_lines (
    id UUID PRIMARY KEY,
    entry_id UUID NOT NULL REFERENCES cashbook_entries(id) ON DELETE CASCADE,
    account_id UUID NOT NULL REFERENCES cashbook_accounts(id),
    debit NUMERIC(14, 2) NOT NULL DEFAULT 0,
    credit NUMERIC(14, 2) NOT NULL DEFAULT 0,
    created_at TIMESTAMP,
    CONSTRAINT ck_cashbook_lines_one_side
        CHECK ((debit > 0 AND credit = 0) OR (credit > 0 AND debit = 0))
);

CREATE INDEX IF NOT EXISTS ix_cashbook_lines_account_id ON cashbook_lines (account_id);
CREATE INDEX IF NOT EXISTS ix_cashbook_lines_entry_id ON cashbook_lines (entry_id);

CREATE TABLE IF NOT EXISTS cashbook_period_locks (
    id UUID PRIMARY KEY,
    period_start DATE NOT NULL UNIQUE,
    locked_by_user_id UUID REFERENCES users(id),
    locked_at TIMESTAMP,
    note TEXT
);

ALTER TABLE member_settlements
    ADD COLUMN IF NOT EXISTS paid_from settlementpaymentmethod;

-- Starter chart. System accounts are the ones the automatic postings
-- name; the rest cover the workbook's income and expenditure heads and
-- can be added to or deactivated from the cashbook screen.
INSERT INTO cashbook_accounts (id, code, name, kind, system_key, is_active, created_at)
VALUES
    (gen_random_uuid(), '1000', 'Cash on hand', 'asset', 'CASH', true, now()),
    (gen_random_uuid(), '1010', 'Bank', 'asset', 'BANK', true, now()),
    (gen_random_uuid(), '1100', 'Loans receivable', 'asset', 'LOAN_RECEIVABLE', true, now()),
    (gen_random_uuid(), '1200', 'Furniture', 'asset', NULL, true, now()),
    (gen_random_uuid(), '1210', 'Computer equipment', 'asset', NULL, true, now()),
    (gen_random_uuid(), '1220', 'Printer', 'asset', NULL, true, now()),
    (gen_random_uuid(), '2000', 'Member savings', 'liability', 'MEMBER_SAVINGS', true, now()),
    (gen_random_uuid(), '2010', 'Payouts payable', 'liability', 'PAYOUT_PAYABLE', true, now()),
    (gen_random_uuid(), '2020', 'Other deductions payable', 'liability', 'OTHER_DEDUCTIONS_PAYABLE', true, now()),
    (gen_random_uuid(), '3000', 'Retained earnings', 'equity', 'RETAINED_EARNINGS', true, now()),
    (gen_random_uuid(), '3010', 'Reserve', 'equity', NULL, true, now()),
    (gen_random_uuid(), '4000', 'Loan interest income', 'income', 'INTEREST_INCOME', true, now()),
    (gen_random_uuid(), '4010', 'Loan fee income', 'income', 'LOAN_FEE_INCOME', true, now()),
    (gen_random_uuid(), '4020', 'Default charge income', 'income', 'DEFAULT_CHARGE_INCOME', true, now()),
    (gen_random_uuid(), '4030', 'Registration fees', 'income', NULL, true, now()),
    (gen_random_uuid(), '4040', 'Other income', 'income', NULL, true, now()),
    (gen_random_uuid(), '5000', 'Exco sitting allowance', 'expense', NULL, true, now()),
    (gen_random_uuid(), '5010', 'Administrative expenses', 'expense', NULL, true, now()),
    (gen_random_uuid(), '5020', 'Deduction logistics', 'expense', NULL, true, now()),
    (gen_random_uuid(), '5030', 'Transportation and airtime', 'expense', NULL, true, now()),
    (gen_random_uuid(), '5040', 'Remittances to departments', 'expense', NULL, true, now()),
    (gen_random_uuid(), '5050', 'Bank charges', 'expense', NULL, true, now()),
    (gen_random_uuid(), '5060', 'AGM', 'expense', NULL, true, now()),
    (gen_random_uuid(), '5070', 'Other expenditure', 'expense', NULL, true, now())
ON CONFLICT DO NOTHING;
