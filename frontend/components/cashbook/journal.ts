import type { CashbookLineInput } from "@/lib/api";

export interface JournalLineDraft {
  key: string;
  accountId: string;
  debit: string;
  credit: string;
}

let nextKey = 0;

export function newJournalLine(): JournalLineDraft {
  nextKey += 1;
  return { key: `line-${nextKey}`, accountId: "", debit: "", credit: "" };
}

export function emptyJournal(): JournalLineDraft[] {
  return [newJournalLine(), newJournalLine()];
}

function amount(value: string): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : 0;
}

export function lineTotals(lines: JournalLineDraft[]): {
  debit: number;
  credit: number;
  balanced: boolean;
} {
  const debit = lines.reduce((sum, line) => sum + amount(line.debit), 0);
  const credit = lines.reduce((sum, line) => sum + amount(line.credit), 0);
  return { debit, credit, balanced: debit > 0 && debit === credit };
}

/**
 * Turn the drafts into what the server expects, or explain what is wrong.
 * Rows with no amount are dropped, so an unused blank row never blocks a
 * submission; a row with an amount but no account does.
 */
export function journalLinesToInput(
  lines: JournalLineDraft[]
): { ok: true; lines: CashbookLineInput[] } | { ok: false; error: string } {
  const used = lines.filter((line) => amount(line.debit) > 0 || amount(line.credit) > 0);

  for (const line of used) {
    if (!line.accountId) return { ok: false, error: "Choose an account for every line with an amount." };
    if (amount(line.debit) > 0 && amount(line.credit) > 0) {
      return { ok: false, error: "A line is either a debit or a credit, not both." };
    }
  }
  if (used.length < 2) {
    return { ok: false, error: "A journal entry needs at least two lines." };
  }

  const totals = lineTotals(used);
  if (totals.debit <= 0 || totals.credit <= 0) {
    return { ok: false, error: "An entry needs at least one debit and one credit." };
  }
  if (!totals.balanced) {
    return {
      ok: false,
      error: `Debits and credits must match (${totals.debit.toFixed(2)} vs ${totals.credit.toFixed(2)}).`,
    };
  }

  return {
    ok: true,
    lines: used.map((line) => ({
      account_id: line.accountId,
      debit: amount(line.debit) > 0 ? line.debit : "0",
      credit: amount(line.credit) > 0 ? line.credit : "0",
    })),
  };
}
