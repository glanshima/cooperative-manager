import { describe, expect, it } from "vitest";

import { journalLinesToInput, lineTotals, newJournalLine } from "./journal";

function line(accountId: string, debit = "", credit = "") {
  return { ...newJournalLine(), accountId, debit, credit };
}

describe("journal line validation", () => {
  it("accepts a balanced entry and drops blank rows", () => {
    const result = journalLinesToInput([
      line("bank", "1000", ""),
      line("income", "", "1000"),
      line(""),
    ]);

    expect(result.ok).toBe(true);
    if (!result.ok) return;
    expect(result.lines).toEqual([
      { account_id: "bank", debit: "1000", credit: "0" },
      { account_id: "income", debit: "0", credit: "1000" },
    ]);
  });

  it("rejects an entry whose sides do not match", () => {
    const result = journalLinesToInput([line("bank", "1000", ""), line("income", "", "900")]);

    expect(result).toEqual({
      ok: false,
      error: "Debits and credits must match (1000.00 vs 900.00).",
    });
  });

  it("rejects a line that carries both a debit and a credit", () => {
    const result = journalLinesToInput([line("bank", "100", "100"), line("income", "", "0")]);

    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.error).toMatch(/either a debit or a credit/);
  });

  it("rejects an amount with no account chosen", () => {
    const result = journalLinesToInput([line("", "50", ""), line("income", "", "50")]);

    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.error).toMatch(/Choose an account/);
  });

  it("needs at least two lines with amounts", () => {
    expect(journalLinesToInput([line("bank", "50", ""), line("")]).ok).toBe(false);
  });

  it("totals only positive amounts", () => {
    const totals = lineTotals([line("a", "500", ""), line("b", "", "500"), line("c", "-20", "")]);

    expect(totals.debit).toBe(500);
    expect(totals.credit).toBe(500);
    expect(totals.balanced).toBe(true);
  });
});
