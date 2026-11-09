import { apiFetch } from "./client";
import type { MemberStatus } from "./members";

export type PayrollDeductionStatus =
  | "draft"
  | "submitted"
  | "confirmed"
  | "not_deducted"
  | "void";

export type PayrollDeductionLineCategory = "monthly_contribution" | "loan_repayment" | "other";

export interface PayrollDeductionLine {
  id: string;
  category: PayrollDeductionLineCategory;
  loan_id?: string | null;
  label?: string | null;
  amount: string;
  // What the server computed this line should be for its month. Null when
  // nothing on file predicts it; a different amount is an override.
  expected_amount?: string | null;
  loan_type_name?: string | null;
}

export interface PayrollDeduction {
  id: string;
  member_id: string;
  member_name?: string | null;
  member_psn?: string | null;
  deduction_month: string; // YYYY-MM-01
  payroll_reference?: string | null;
  note?: string | null;
  status: PayrollDeductionStatus;
  contribution_total: string;
  loan_total: string;
  other_total: string;
  grand_total: string;
  submitted_at?: string | null;
  confirmed_at?: string | null;
  not_deducted_at?: string | null;
  not_deducted_reason?: string | null;
  returned_at?: string | null;
  return_reason?: string | null;
  voided_at?: string | null;
  void_reason?: string | null;
  created_at: string;
  updated_at: string;
  // See Member.conflicted -- this month's record stays in the schedule and
  // in every total, but only another officer may act on it.
  conflicted?: boolean;
  lines: PayrollDeductionLine[];
}

export interface PayrollDeductionLineInput {
  category: PayrollDeductionLineCategory;
  loan_id?: string;
  label?: string;
  amount: number;
}

export interface PayrollDeductionCreateInput {
  member_id: string;
  deduction_month: string; // YYYY-MM
  payroll_reference?: string;
  note?: string;
  lines: PayrollDeductionLineInput[];
}

export interface PayrollDeductionUpdateInput {
  deduction_month?: string;
  payroll_reference?: string | null;
  note?: string | null;
  lines?: PayrollDeductionLineInput[];
}

export interface PayrollDeductionTotals {
  contribution_total: string;
  loan_total: string;
  other_total: string;
  grand_total: string;
}

export interface PayrollDeductionSchedule {
  month: string;
  records: PayrollDeduction[];
  totals: PayrollDeductionTotals;
}

export interface PayrollDeductionBulkResult {
  id: string;
  ok: boolean;
  status?: PayrollDeductionStatus | null;
  detail?: string | null;
}

export interface PayrollDeductionBulkResponse {
  results: PayrollDeductionBulkResult[];
}

export type PayrollDeductionBulkAction = "submit" | "confirm" | "not-deducted" | "void";

export interface PayrollDeductionListResult {
  items: PayrollDeduction[];
  total: number;
  skip: number;
  limit: number;
}

export interface DeductionSubmittableIds {
  month: string;
  ids: string[];
  empty_draft_ids: string[];
}

// The ceiling the backend enforces on one bulk call, kept a little below
// the server's max_length so an exact-boundary batch still passes.
export const BULK_CHUNK_SIZE = 25;
export const LEDGER_PAGE_SIZE = 50;

export async function listDeductions(
  params: {
    month?: string;
    status?: PayrollDeductionStatus;
    member_id?: string;
    skip?: number;
    limit?: number;
  } = {}
): Promise<PayrollDeductionListResult> {
  return apiFetch<PayrollDeductionListResult>("/api/payroll-deductions", {
    searchParams: {
      month: params.month,
      status: params.status,
      member_id: params.member_id,
      skip: params.skip !== undefined ? String(params.skip) : undefined,
      limit: params.limit !== undefined ? String(params.limit) : undefined,
    },
  });
}

export async function getSubmittableDeductionIds(month: string): Promise<DeductionSubmittableIds> {
  return apiFetch<DeductionSubmittableIds>("/api/payroll-deductions/submittable-ids", {
    searchParams: { month },
  });
}

export async function getDeductionSchedule(month: string): Promise<PayrollDeductionSchedule> {
  return apiFetch<PayrollDeductionSchedule>("/api/payroll-deductions/schedule", {
    searchParams: { month },
  });
}

export async function getDeduction(id: string): Promise<PayrollDeduction> {
  return apiFetch<PayrollDeduction>(`/api/payroll-deductions/${id}`);
}

export async function createDeduction(input: PayrollDeductionCreateInput): Promise<PayrollDeduction> {
  return apiFetch<PayrollDeduction>("/api/payroll-deductions", { method: "POST", body: input });
}

export async function updateDeduction(
  id: string,
  input: PayrollDeductionUpdateInput
): Promise<PayrollDeduction> {
  return apiFetch<PayrollDeduction>(`/api/payroll-deductions/${id}`, { method: "PUT", body: input });
}

export async function submitDeduction(id: string): Promise<PayrollDeduction> {
  return apiFetch<PayrollDeduction>(`/api/payroll-deductions/${id}/submit`, { method: "POST" });
}

export async function returnDeductionToDraft(id: string, reason: string): Promise<PayrollDeduction> {
  return apiFetch<PayrollDeduction>(`/api/payroll-deductions/${id}/return-to-draft`, {
    method: "POST",
    body: { reason },
  });
}

export async function confirmDeduction(id: string): Promise<PayrollDeduction> {
  return apiFetch<PayrollDeduction>(`/api/payroll-deductions/${id}/confirm`, { method: "POST" });
}

export async function markDeductionNotDeducted(id: string, reason: string): Promise<PayrollDeduction> {
  return apiFetch<PayrollDeduction>(`/api/payroll-deductions/${id}/not-deducted`, {
    method: "POST",
    body: { reason },
  });
}

export async function voidDeduction(id: string, reason: string): Promise<PayrollDeduction> {
  return apiFetch<PayrollDeduction>(`/api/payroll-deductions/${id}/void`, {
    method: "POST",
    body: { reason },
  });
}

export async function bulkDeductions(
  action: PayrollDeductionBulkAction,
  ids: string[],
  reason?: string
): Promise<PayrollDeductionBulkResponse> {
  return apiFetch<PayrollDeductionBulkResponse>(`/api/payroll-deductions/bulk/${action}`, {
    method: "POST",
    body: { ids, reason },
  });
}

// --- Enter queue (worklist) ---
// Who still needs entering for a month, with the amounts the server expects.
// The queue shrinks as drafts are created; expected amounts come from the
// backend so the officer never has to compute an instalment by hand.

export interface DeductionWorklistLine {
  category: PayrollDeductionLineCategory;
  amount: string;
  loan_id?: string | null;
  loan_type_name?: string | null;
  arrears: string;
  months_behind: number;
}

export interface DeductionWorklistItem {
  member_id: string;
  member_name: string;
  member_psn: string;
  member_status: MemberStatus;
  membership_exit_date?: string | null;
  due_reasons: string[];
  lines: DeductionWorklistLine[];
  warnings: string[];
  expected_total: string;
  deduction_id?: string | null;
  deduction_status?: PayrollDeductionStatus | null;
  conflicted: boolean;
}

export interface DeductionWorklistOut {
  month: string;
  items: DeductionWorklistItem[];
  due_count: number;
  entered_count: number;
  expected_total: string;
}

export async function getDeductionWorklist(
  month: string,
  includeEntered = false
): Promise<DeductionWorklistOut> {
  return apiFetch<DeductionWorklistOut>("/api/payroll-deductions/worklist", {
    searchParams: { month, include_entered: includeEntered ? "true" : undefined },
  });
}
