import { apiFetch } from "./client";

export type DividendBasis =
  | "none"
  | "net_savings_closing"
  | "net_savings_average"
  | "declared_rate_on_savings"
  | "share_capital"
  | "patronage"
  | "equal"
  | "hybrid";

export type DividendPoolMode = "net_income_share" | "savings_percent" | "fixed_amount";

export type DividendRunStatus = "draft" | "declared" | "paid";

export type DividendRounding = "two_dp" | "whole_currency";

export type DividendPayoutMethod = "cash" | "bank";

export type DividendPaymentPolicy = "bank" | "cash" | "either";

export interface DividendRun {
  id: string;
  fiscal_year: number;
  period_start: string;
  period_end: string;
  status: DividendRunStatus;
  basis: DividendBasis;
  pool_mode: DividendPoolMode;
  surplus: string;
  reserve_pct: string;
  reserve_amount: string;
  honorarium_pct: string;
  honorarium_amount: string;
  payout_pct: string;
  pool_amount: string;
  declared_rate_pct?: string | null;
  fixed_pool_amount?: string | null;
  hybrid_savings_pct: string;
  withholding_pct: string;
  rounding: DividendRounding;
  min_membership_months: number;
  include_exited: boolean;
  closed_income_total: string;
  closed_expense_total: string;
  total_basis_amount: string;
  total_gross: string;
  total_withholding: string;
  total_net: string;
  rounding_residual: string;
  eligible_member_count: number;
  note?: string | null;
  declared_on?: string | null;
  declared_by_user_id?: string | null;
  created_at?: string | null;
}

export interface DividendAllocation {
  id: string;
  member_id: string;
  psn: string;
  name: string;
  bank_name?: string | null;
  account_number?: string | null;
  basis_amount: string;
  share_ratio: string;
  gross_amount: string;
  withholding_amount: string;
  net_amount: string;
  rounding_adjustment: string;
  payout_id?: string | null;
}

export interface DividendAllocationPage {
  items: DividendAllocation[];
  total: number;
  skip: number;
  limit: number;
}

export interface DividendPayout {
  id: string;
  run_id: string;
  paid_on: string;
  method: DividendPayoutMethod;
  reference: string;
  amount: string;
  note?: string | null;
  created_by_user_id?: string | null;
  created_at?: string | null;
}

export interface DividendRunDetail {
  run: DividendRun;
  payouts: DividendPayout[];
  paid_allocations: number;
  pending_allocations: number;
}

export interface DividendManifestRow {
  psn: string;
  name: string;
  bank_name?: string | null;
  account_number?: string | null;
  gross_amount: string;
  withholding_amount: string;
  net_amount: string;
  payout_id?: string | null;
}

export interface DividendManifest {
  fiscal_year: number;
  reference: string;
  rows: DividendManifestRow[];
  total_gross: string;
  total_withholding: string;
  total_net: string;
}

export interface DividendSummary {
  fiscal_year_start_month: number;
  basis: DividendBasis;
  pool_mode: DividendPoolMode;
  reserve_pct: string;
  honorarium_pct: string;
  payout_pct: string;
  declared_rate_pct?: string | null;
  fixed_pool_amount?: string | null;
  hybrid_savings_pct: string;
  min_membership_months: number;
  include_exited: boolean;
  rounding: DividendRounding;
  withholding_pct: string;
  payment_method: DividendPaymentPolicy;
  cashbook_module_enabled: boolean;
  cashbook_open: boolean;
  last_declared_year?: number | null;
  suggested_fiscal_year: number;
}

export interface DividendPayoutInput {
  paid_on?: string;
  method: DividendPayoutMethod;
  reference: string;
  note?: string;
  // Omit to pay every pending allocation in one batch.
  allocation_ids?: string[];
}

export async function getDividendSummary(): Promise<DividendSummary> {
  return apiFetch<DividendSummary>("/api/dividends/summary");
}

export async function listDividendRuns(): Promise<DividendRun[]> {
  return apiFetch<DividendRun[]>("/api/dividends/runs");
}

export async function createDividendRun(input: {
  fiscal_year: number;
  note?: string;
}): Promise<DividendRun> {
  return apiFetch<DividendRun>("/api/dividends/runs", { method: "POST", body: input });
}

export async function getDividendRun(id: string): Promise<DividendRunDetail> {
  return apiFetch<DividendRunDetail>(`/api/dividends/runs/${id}`);
}

export async function recomputeDividendRun(id: string, note?: string): Promise<DividendRun> {
  return apiFetch<DividendRun>(`/api/dividends/runs/${id}`, {
    method: "PATCH",
    body: { note },
  });
}

export async function deleteDividendRun(id: string): Promise<void> {
  return apiFetch<void>(`/api/dividends/runs/${id}`, { method: "DELETE" });
}

export async function listDividendAllocations(
  id: string,
  params: { q?: string; skip?: number; limit?: number } = {}
): Promise<DividendAllocationPage> {
  return apiFetch<DividendAllocationPage>(`/api/dividends/runs/${id}/allocations`, {
    searchParams: {
      q: params.q,
      skip: params.skip !== undefined ? String(params.skip) : undefined,
      limit: params.limit !== undefined ? String(params.limit) : undefined,
    },
  });
}

export async function declareDividendRun(id: string, declaredOn?: string): Promise<DividendRun> {
  return apiFetch<DividendRun>(`/api/dividends/runs/${id}/declare`, {
    method: "POST",
    body: { declared_on: declaredOn },
  });
}

export async function recordDividendPayout(
  id: string,
  input: DividendPayoutInput
): Promise<DividendPayout> {
  return apiFetch<DividendPayout>(`/api/dividends/runs/${id}/payouts`, {
    method: "POST",
    body: input,
  });
}

export async function getDividendManifest(id: string): Promise<DividendManifest> {
  return apiFetch<DividendManifest>(`/api/dividends/runs/${id}/manifest`);
}
