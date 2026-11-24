import type {
  DividendBasis,
  DividendPayoutMethod,
  DividendPaymentPolicy,
  DividendPoolMode,
  DividendRounding,
  DividendRunStatus,
} from "@/lib/api";

export const RUN_STATUS_LABELS: Record<DividendRunStatus, string> = {
  draft: "Draft",
  declared: "Declared",
  paid: "Paid",
};

export const RUN_STATUS_COLORS: Record<DividendRunStatus, string> = {
  draft: "#8a6d00",
  declared: "green",
  paid: "#555",
};

export const BASIS_LABELS: Record<DividendBasis, string> = {
  none: "No basis chosen",
  net_savings_closing: "Closing net savings",
  net_savings_average: "Average net savings",
  declared_rate_on_savings: "Declared rate on savings",
  share_capital: "Share capital",
  patronage: "Loan interest paid",
  equal: "Equal share per member",
  hybrid: "Hybrid: savings and loan interest",
};

export const POOL_LABELS: Record<DividendPoolMode, string> = {
  net_income_share: "Share of the year's surplus",
  savings_percent: "Percentage of total savings",
  fixed_amount: "Fixed amount",
};

export const ROUNDING_LABELS: Record<DividendRounding, string> = {
  two_dp: "To the kobo",
  whole_currency: "To the whole naira",
};

export const PAYOUT_METHOD_LABELS: Record<DividendPayoutMethod, string> = {
  cash: "Cash",
  bank: "Bank transfer",
};

export const PAYMENT_POLICY_LABELS: Record<DividendPaymentPolicy, string> = {
  bank: "Bank transfer only",
  cash: "Cash only",
  either: "Cash or bank",
};

export function todayIso(): string {
  return new Date().toISOString().slice(0, 10);
}

// The hybrid basis stores a weighted score rather than money, so it is
// shown as a plain score instead of a naira figure.
export function formatBasis(basis: DividendBasis, value: string): string {
  const amount = Number(value);
  if (!Number.isFinite(amount)) return value;
  if (basis === "hybrid") return amount.toFixed(4);
  return amount.toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}
