import { apiFetch } from "./client";

// Figures arrive as Decimal-as-string, matching every other money field in
// the app. A section is `null` when the account may not see it -- that is a
// permission/module answer, never "zero".
export type DashboardPeriodKey = "this_month" | "last_month" | "this_year" | "last_year";

export interface DashboardPeriod {
  key: DashboardPeriodKey;
  label: string;
  start: string;
  end: string;
}

export interface DashboardMembers {
  total: number;
  financial: number;
  non_financial: number;
  exited: number;
  joined: number;
}

export interface DashboardSavings {
  total: string;
  collected: string;
  paid_out: string;
}

export interface DashboardRepayments {
  count: number;
  amount: string;
}

export interface DashboardLoans {
  active_count: number;
  // total_repayable - amount_repaid: outstanding includes interest.
  outstanding: string;
  defaulted_count: number;
  disbursed_count: number;
  disbursed: string;
  repayments: DashboardRepayments | null;
}

export interface DashboardDeductions {
  confirmed_total: string;
  confirmed_members: number;
  draft_count: number;
  submitted_count: number;
}

export interface DashboardCashbook {
  books_open: boolean;
  cash: string | null;
  bank: string | null;
  total: string | null;
}

export interface DashboardDividends {
  last_declared_year: number | null;
  last_declared_on: string | null;
  last_pool: string | null;
  unpaid_net: string;
  paid_net: string;
}

export interface DashboardQueue {
  key: string;
  label: string;
  count: number;
  amount: string | null;
  href: string;
}

export interface DashboardActivity {
  event_type: string;
  action: string;
  actor: string;
  entity_type: string | null;
  entity_id: string | null;
  timestamp: string;
}

export interface DashboardTrend {
  months: string[];
  savings: string[] | null;
  repayments: string[] | null;
}

export interface AdminDashboard {
  period: DashboardPeriod;
  members: DashboardMembers | null;
  savings: DashboardSavings | null;
  loans: DashboardLoans | null;
  deductions: DashboardDeductions | null;
  cashbook: DashboardCashbook | null;
  dividends: DashboardDividends | null;
  queues: DashboardQueue[];
  activity: DashboardActivity[] | null;
  trend: DashboardTrend | null;
}

export function getAdminDashboard(period: DashboardPeriodKey): Promise<AdminDashboard> {
  return apiFetch<AdminDashboard>("/api/admin/dashboard", { searchParams: { period } });
}
