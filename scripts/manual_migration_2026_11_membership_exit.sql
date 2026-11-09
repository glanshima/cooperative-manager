-- MACT Cooperative Manager -- membership exit (withdrawal) state.
--
-- Member.status only says financial / non_financial, which cannot tell a
-- member who formally left the cooperative apart from one who merely
-- fell behind on contributions. Both stop owing the monthly
-- contribution, but only the exit is permanent, and the payroll
-- deduction queue needs to say why someone is still being deducted loan
-- repayments.
--
-- Purely additive; existing members keep a NULL exit date, i.e. "never
-- exited", which is also the correct reading of every record imported
-- from the spreadsheet.

ALTER TABLE members
    ADD COLUMN IF NOT EXISTS membership_exit_date DATE,
    ADD COLUMN IF NOT EXISTS membership_exit_reason VARCHAR;
