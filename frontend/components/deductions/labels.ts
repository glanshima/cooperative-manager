import type { PayrollDeductionStatus } from "@/lib/api";

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

export function monthLabel(value: string): string {
  const [year, month] = value.split("-").map(Number);
  if (!year || !month) return value;
  return new Date(year, month - 1, 1).toLocaleDateString(undefined, {
    month: "long",
    year: "numeric",
  });
}

export function currentMonth(): string {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;
}
