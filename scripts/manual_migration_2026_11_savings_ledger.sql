-- Member savings ledger and exit settlement (2026-11).
--
-- Member savings was previously "the sum of confirmed monthly_contribution
-- payroll lines": fine for a balance, useless when the cooperative must
-- actually debit it. Three tables add the missing subledger:
--
-- 1. savings_entries -- append-only. Each row names what happened
--    ('contribution', 'contribution_reversal', 'exit_offset',
--    'exit_payout') and the balance is the sum of the rows. Contributions
--    link the payroll line that produced them, unique per entry kind, so
--    a confirmed month can never be posted twice and its reversal is a
--    separate row rather than an edit.
--
-- 2. member_settlements -- one per member, written when an exiting
--    member's savings are applied to their loans (oldest loan first) and
--    the remainder is paid out. Figures are snapshots: savings at
--    settlement, total offset, payout amount, and whether that payout has
--    been handed over yet.
--
-- 3. settlement_allocations -- how much of one settlement went to each
--    loan, so a loan's history can always be traced back to the exit.
--
-- The backfill posts every existing confirmed contribution line as a
-- ledger entry, so a deployment's savings balances do not move when this
-- lands. Re-running the file re-posts nothing.

DO $$
BEGIN
    CREATE TYPE savingsentrytype AS ENUM (
        'contribution', 'contribution_reversal', 'exit_offset', 'exit_payout'
    );
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

DO $$
BEGIN
    CREATE TYPE settlementpayoutstatus AS ENUM ('pending', 'paid');
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

CREATE TABLE IF NOT EXISTS member_settlements (
    id UUID PRIMARY KEY,
    member_id UUID NOT NULL UNIQUE REFERENCES members(id) ON DELETE CASCADE,
    settled_on DATE NOT NULL,
    settled_by_user_id UUID REFERENCES users(id),
    settled_at TIMESTAMP,
    savings_balance NUMERIC(14, 2) NOT NULL,
    offset_total NUMERIC(14, 2) NOT NULL,
    payout_amount NUMERIC(14, 2) NOT NULL,
    payout_status settlementpayoutstatus NOT NULL DEFAULT 'pending',
    paid_on DATE,
    paid_at TIMESTAMP,
    paid_reference VARCHAR,
    note TEXT
);

DO $$
BEGIN
    ALTER TABLE member_settlements
        ADD CONSTRAINT ck_member_settlements_savings_nonnegative
        CHECK (savings_balance >= 0);
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

DO $$
BEGIN
    ALTER TABLE member_settlements
        ADD CONSTRAINT ck_member_settlements_offset_nonnegative
        CHECK (offset_total >= 0);
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

DO $$
BEGIN
    ALTER TABLE member_settlements
        ADD CONSTRAINT ck_member_settlements_payout_nonnegative
        CHECK (payout_amount >= 0);
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

CREATE TABLE IF NOT EXISTS settlement_allocations (
    id UUID PRIMARY KEY,
    settlement_id UUID NOT NULL REFERENCES member_settlements(id) ON DELETE CASCADE,
    loan_id UUID NOT NULL REFERENCES loans(id),
    amount NUMERIC(14, 2) NOT NULL,
    created_at TIMESTAMP,
    CONSTRAINT ck_settlement_allocations_amount_positive CHECK (amount > 0),
    CONSTRAINT uq_settlement_allocations_loan UNIQUE (settlement_id, loan_id)
);

CREATE TABLE IF NOT EXISTS savings_entries (
    id UUID PRIMARY KEY,
    member_id UUID NOT NULL REFERENCES members(id) ON DELETE CASCADE,
    entry_type savingsentrytype NOT NULL,
    amount NUMERIC(14, 2) NOT NULL,
    deduction_line_id UUID REFERENCES payroll_deduction_lines(id) ON DELETE CASCADE,
    settlement_id UUID REFERENCES member_settlements(id) ON DELETE CASCADE,
    posted_by_user_id UUID REFERENCES users(id),
    posted_at TIMESTAMP,
    note TEXT,
    CONSTRAINT ck_savings_entries_amount_positive CHECK (amount > 0),
    CONSTRAINT uq_savings_entries_line_kind UNIQUE (deduction_line_id, entry_type)
);

CREATE INDEX IF NOT EXISTS ix_savings_entries_member_id ON savings_entries (member_id);
CREATE INDEX IF NOT EXISTS ix_savings_entries_settlement_id ON savings_entries (settlement_id);

-- Every confirmed contribution line becomes one ledger entry. The
-- NOT EXISTS guard keeps re-runs (and databases where the app has already
-- posted some lines) from doubling a member's balance.
INSERT INTO savings_entries (
    id, member_id, entry_type, amount, deduction_line_id, posted_at, note
)
SELECT
    gen_random_uuid(),
    d.member_id,
    'contribution',
    l.amount,
    l.id,
    COALESCE(d.confirmed_at, d.created_at, now()),
    'Backfilled from a confirmed payroll deduction'
FROM payroll_deduction_lines l
JOIN payroll_deductions d ON d.id = l.deduction_id
WHERE l.category = 'monthly_contribution'
  AND d.status = 'confirmed'
  AND NOT EXISTS (
      SELECT 1
      FROM savings_entries e
      WHERE e.deduction_line_id = l.id
        AND e.entry_type = 'contribution'
  );
