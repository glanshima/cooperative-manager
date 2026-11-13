import type { LoanLineCategory, PayrollDeductionStatus } from "@/lib/api";

export const STATUS_LABELS: Record<PayrollDeductionStatus, string> = {
  draft: "Draft",
  submitted: "Submitted",
  confirmed: "Confirmed",
  not_deducted: "Not deducted",
  void: "Void",
};

export const STATUS_COLORS: Record<PayrollDeductionStatus, string> = {
  draft: "#555",
  submitted: "#8a6d00",
  confirmed: "green",
  not_deducted: "#a33",
  void: "#777",
};

export function formatMoney(value: string | number): string {
  const amount = typeof value === "number" ? value : Number(value);
  if (!Number.isFinite(amount)) return String(value);
  return amount.toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

// A loan can owe two things in one month, and payroll needs to see them
// apart: this month's instalment, and the arrears line catching up earlier
// ones.
export function loanLineName(category: LoanLineCategory, loanTypeName?: string | null): string {
  const name = loanTypeName ?? "Loan";
  return category === "loan_arrears" ? `Arrears on ${name}` : name;
}

export function monthsBehind(count: number): string {
  return `${count} month${count === 1 ? "" : "s"} behind`;
}
