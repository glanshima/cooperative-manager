import type { CashbookAccountKind, CashbookEntrySource } from "@/lib/api";

export const KIND_LABELS: Record<CashbookAccountKind, string> = {
  asset: "Asset",
  liability: "Liability",
  equity: "Equity",
  income: "Income",
  expense: "Expense",
};

// Assets and expenses sit on the debit side; the rest on the credit side.
// The server reports every balance already normalised to that side.
export const KIND_ORDER: CashbookAccountKind[] = [
  "asset",
  "liability",
  "equity",
  "income",
  "expense",
];

export const SOURCE_LABELS: Record<CashbookEntrySource, string> = {
  manual: "Manual",
  opening: "Opening",
  reversal: "Reversal",
  payroll_deduction: "Payroll deduction",
  payroll_deduction_void: "Deduction void",
  loan_disbursement: "Loan disbursement",
  loan_repayment: "Loan repayment",
  loan_fee: "Loan fee",
  settlement: "Exit settlement",
  settlement_payout: "Settlement payout",
};

export function todayIso(): string {
  return new Date().toISOString().slice(0, 10);
}

export function monthStartIso(offsetMonths = 0): string {
  const now = new Date();
  const value = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth() + offsetMonths, 1));
  return value.toISOString().slice(0, 10);
}

// Formats a "YYYY-MM-01" period start (or any date in that month) as
// "November 2026" without letting the local timezone shift the month.
export function monthLabel(isoDate: string): string {
  const [year, month] = isoDate.split("-").map(Number);
  return new Date(Date.UTC(year, month - 1, 1)).toLocaleString(undefined, {
    month: "long",
    year: "numeric",
    timeZone: "UTC",
  });
}
