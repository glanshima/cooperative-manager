import { apiFetch } from "./client";

// How (and whether) interest is taken out of the disbursed amount.
// at_source: withheld from the payout, member repays the principal.
// spread_over_tenure: full payout, interest in every instalment.
// spread_first_months: full payout, interest folded into the first N.
export type InterestDeductionMode = "at_source" | "spread_over_tenure" | "spread_first_months";

export interface LoanType {
  id: string;
  name: string;
  description?: string | null;
  interest_rate: string; // decimal fraction as string, e.g. "0.1500" - current effective rate (cached)
  tenure_months: number;
  // Processing fee, paid separately: never deducted from the loan and never
  // added to what the member repays.
  flat_charge: string;
  // null = inherit the cooperative default.
  interest_mode?: InterestDeductionMode | null;
  interest_spread_months?: number | null;
  is_active: boolean;
  open_for_application: boolean;
  created_at: string;
  updated_at: string;
}

export interface LoanTypeCreateInput {
  name: string;
  description?: string;
  interest_rate: number;
  tenure_months: number;
  flat_charge?: number;
  interest_mode?: InterestDeductionMode | null;
  interest_spread_months?: number | null;
  is_active?: boolean;
  open_for_application?: boolean;
  effective_from?: string; // ISO date; defaults to today if omitted
}

export interface LoanTypeUpdateInput {
  name?: string;
  description?: string;
  is_active?: boolean;
  open_for_application?: boolean;
}

export interface LoanTypeRateVersion {
  id: string;
  loan_type_id: string;
  interest_rate: string;
  tenure_months: number;
  flat_charge: string;
  interest_mode?: InterestDeductionMode | null;
  interest_spread_months?: number | null;
  effective_from: string;
  created_at: string;
}

export interface LoanTypeRateVersionInput {
  interest_rate: number;
  tenure_months: number;
  flat_charge?: number;
  interest_mode?: InterestDeductionMode | null;
  interest_spread_months?: number | null;
  effective_from: string; // ISO date, can be future-dated to schedule a change
}

export async function listLoanTypes(): Promise<LoanType[]> {
  return apiFetch<LoanType[]>("/api/loan-types");
}

export async function createLoanType(input: LoanTypeCreateInput): Promise<LoanType> {
  return apiFetch<LoanType>("/api/loan-types", { method: "POST", body: input });
}

export async function updateLoanType(id: string, input: LoanTypeUpdateInput): Promise<LoanType> {
  return apiFetch<LoanType>(`/api/loan-types/${id}`, { method: "PUT", body: input });
}

export async function deleteLoanType(id: string): Promise<void> {
  return apiFetch<void>(`/api/loan-types/${id}`, { method: "DELETE" });
}

export async function listRateVersions(loanTypeId: string): Promise<LoanTypeRateVersion[]> {
  return apiFetch<LoanTypeRateVersion[]>(`/api/loan-types/${loanTypeId}/rate-versions`);
}

export async function createRateVersion(
  loanTypeId: string,
  input: LoanTypeRateVersionInput
): Promise<LoanTypeRateVersion> {
  return apiFetch<LoanTypeRateVersion>(`/api/loan-types/${loanTypeId}/rate-versions`, {
    method: "POST",
    body: input,
  });
}

export type LoanStatus = "active" | "completed" | "defaulted";

export interface Loan {
  id: string;
  member_id: string;
  loan_type_id: string;
  principal: string;
  interest_amount: string;
  net_disbursed: string;
  total_repayable: string;
  monthly_installment: string;
  // Snapshot of the rules agreed at disbursement.
  interest_mode?: InterestDeductionMode;
  interest_spread_months?: number | null;
  // Extra amount on each of the first interest_spread_months instalments.
  interest_installment?: string;
  // Processing fee owed separately; fee_status tracks its own payment.
  fee_amount?: string;
  fee_status?: "not_required" | "due" | "awaiting_verification" | "rejected" | "paid";
  fee_rejection_reason?: string | null;
  disbursement_date: string;
  expected_end_date: string;
  disbursement_bank_name?: string | null;
  disbursement_account_name?: string | null;
  disbursement_account_number?: string | null;
  amount_repaid: string;
  status: LoanStatus;
  notes?: string | null;
  member_name: string;
  member_psn: string;
  loan_type_name: string;
  balance: string;
  created_at: string;
  updated_at: string;
  // See Member.conflicted -- visible to a conflicted officer, read-only.
  conflicted?: boolean;
}

export interface LoanInput {
  member_id: string;
  loan_type_id: string;
  principal: number;
  disbursement_date: string; // ISO date, e.g. "2026-08-01"
  notes?: string;
}

export async function listLoans(params?: { member_id?: string; status?: LoanStatus }): Promise<Loan[]> {
  return apiFetch<Loan[]>("/api/loans", { searchParams: params });
}

/** Server-computed total across the member's active loans -- never re-derived here. */
export interface MemberLoanBalance {
  member_id: string;
  active_loan_count: number;
  total_outstanding_balance: string;
  conflicted: boolean;
}

export async function getMemberLoanBalance(memberId: string): Promise<MemberLoanBalance> {
  return apiFetch<MemberLoanBalance>(`/api/loans/member/${memberId}/balance`);
}

export async function createLoan(input: LoanInput): Promise<Loan> {
  return apiFetch<Loan>("/api/loans", { method: "POST", body: input });
}

export async function updateLoan(
  id: string,
  input: Partial<{ amount_repaid: number; status: LoanStatus; notes: string }>
): Promise<Loan> {
  return apiFetch<Loan>(`/api/loans/${id}`, { method: "PUT", body: input });
}

export async function deleteLoan(id: string): Promise<void> {
  return apiFetch<void>(`/api/loans/${id}`, { method: "DELETE" });
}
