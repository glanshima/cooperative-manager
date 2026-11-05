import { apiFetch } from "./client";

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

export async function listDeductions(params: {
  month?: string;
  status?: PayrollDeductionStatus;
  member_id?: string;
} = {}): Promise<PayrollDeduction[]> {
  return apiFetch<PayrollDeduction[]>("/api/payroll-deductions", { searchParams: params });
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
