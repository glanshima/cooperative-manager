import { apiFetch } from "./client";

export type LoanApplicationStatus = "pending" | "approved" | "rejected" | "cancelled";
export type PaymentVerificationStatus = "awaiting_verification" | "verified" | "rejected";

export interface LoanApplication {
  id: string;
  member_id: string;
  loan_type_id: string;
  requested_amount: string;
  approved_amount?: string | null;
  requested_tenure_months?: number | null;
  approved_tenure_months?: number | null;
  tenure_decision_reason?: string | null;
  preferred_disbursement_date?: string | null;
  use_default_account: boolean;
  alternate_bank_name?: string | null;
  alternate_account_name?: string | null;
  alternate_account_number?: string | null;
  status: LoanApplicationStatus;
  member_notes?: string | null;
  admin_notes?: string | null;
  was_restricted_at_submission: boolean;
  restriction_reason_snapshot?: string | null;
  form_fee_amount: string;
  payment_reference: string;
  receipt_content_type: string;
  payment_status: PaymentVerificationStatus;
  payment_verified_at?: string | null;
  payment_rejection_reason?: string | null;
  reviewed_at?: string | null;
  resulting_loan_id?: string | null;
  cancelled_at?: string | null;
  can_reapply: boolean;
  reapplied_from_id?: string | null;
  member_name: string;
  member_psn: string;
  loan_type_name: string;
  created_at: string;
  updated_at: string;
  // See Member.conflicted -- visible to a conflicted officer, read-only.
  conflicted?: boolean;
}

export interface LoanApplicationWithReceipt extends LoanApplication {
  receipt_image_base64: string;
}

export interface LoanApplicationInput {
  loan_type_id: string;
  requested_amount: number;
  requested_tenure_months?: number;
  preferred_disbursement_date?: string; // ISO date, preference only
  use_default_account: boolean;
  alternate_bank_name?: string;
  alternate_account_name?: string;
  alternate_account_number?: string;
  member_notes?: string;
  payment_reference: string;
  receipt_image_base64: string;
  receipt_content_type: string;
}

export interface ReapplyInput {
  requested_amount?: number;
  requested_tenure_months?: number;
  preferred_disbursement_date?: string;
  use_default_account: boolean;
  alternate_bank_name?: string;
  alternate_account_name?: string;
  alternate_account_number?: string;
  member_notes?: string;
  payment_reference: string;
  receipt_image_base64: string;
  receipt_content_type: string;
}

export async function listLoanApplications(params?: {
  status?: LoanApplicationStatus;
  payment_status?: PaymentVerificationStatus;
  undisbursed_only?: boolean;
  loan_type_id?: string;
}): Promise<LoanApplication[]> {
  return apiFetch<LoanApplication[]>("/api/loan-applications", {
    searchParams: {
      status: params?.status,
      payment_status: params?.payment_status,
      undisbursed_only: params?.undisbursed_only ? "true" : undefined,
      loan_type_id: params?.loan_type_id,
    },
  });
}

export async function getLoanApplication(id: string): Promise<LoanApplicationWithReceipt> {
  return apiFetch<LoanApplicationWithReceipt>(`/api/loan-applications/${id}`);
}

export async function submitLoanApplication(input: LoanApplicationInput): Promise<LoanApplication> {
  return apiFetch<LoanApplication>("/api/loan-applications", { method: "POST", body: input });
}

export async function verifyPayment(
  id: string,
  approved: boolean,
  rejectionReason?: string
): Promise<LoanApplication> {
  return apiFetch<LoanApplication>(`/api/loan-applications/${id}/verify-payment`, {
    method: "POST",
    body: { approved, rejection_reason: rejectionReason },
  });
}

export async function decideApplication(
  id: string,
  approved: boolean,
  approvedAmount?: number,
  approvedTenureMonths?: number,
  tenureDecisionReason?: string,
  adminNotes?: string,
  canReapply: boolean = true
): Promise<LoanApplication> {
  return apiFetch<LoanApplication>(`/api/loan-applications/${id}/decide`, {
    method: "POST",
    body: {
      approved,
      approved_amount: approvedAmount,
      approved_tenure_months: approvedTenureMonths,
      tenure_decision_reason: tenureDecisionReason,
      admin_notes: adminNotes,
      can_reapply: canReapply,
    },
  });
}

export async function disburseApplication(
  id: string,
  deductLoanIds?: string[],
  deductAllActive?: boolean
): Promise<LoanApplication> {
  return apiFetch<LoanApplication>(`/api/loan-applications/${id}/disburse`, {
    method: "POST",
    body: { deduct_loan_ids: deductLoanIds, deduct_all_active: deductAllActive || false },
  });
}

export async function cancelApplication(id: string): Promise<LoanApplication> {
  return apiFetch<LoanApplication>(`/api/loan-applications/${id}/cancel`, { method: "POST" });
}

export async function rescheduleApplication(
  id: string,
  preferredDisbursementDate: string
): Promise<LoanApplication> {
  return apiFetch<LoanApplication>(`/api/loan-applications/${id}/reschedule`, {
    method: "POST",
    body: { preferred_disbursement_date: preferredDisbursementDate },
  });
}

export async function reapplyLoanApplication(
  id: string,
  input: ReapplyInput
): Promise<LoanApplication> {
  return apiFetch<LoanApplication>(`/api/loan-applications/${id}/reapply`, {
    method: "POST",
    body: input,
  });
}

/** Reads a File (from an <input type="file">) into a base64 string,
 * stripped of the "data:...;base64," prefix, for sending to the API. */
export function fileToBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const result = reader.result as string;
      const base64 = result.split(",")[1] || "";
      resolve(base64);
    };
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });
}
