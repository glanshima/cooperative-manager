import { apiFetch } from "./client";
import type { PaymentVerificationStatus } from "./applications";

export interface LoanRepayment {
  id: string;
  loan_id: string;
  member_id: string;
  amount_claimed: string;
  payment_reference: string;
  receipt_content_type: string;
  status: PaymentVerificationStatus;
  rejection_reason?: string | null;
  verified_at?: string | null;
  created_at: string;
  updated_at: string;
}

export interface LoanRepaymentWithReceipt extends LoanRepayment {
  receipt_image_base64: string;
}

export interface LoanRepaymentInput {
  amount_claimed: number;
  payment_reference: string;
  receipt_image_base64: string;
  receipt_content_type: string;
}

export async function submitRepayment(loanId: string, input: LoanRepaymentInput): Promise<LoanRepayment> {
  return apiFetch<LoanRepayment>(`/api/loans/${loanId}/repayments`, { method: "POST", body: input });
}

export async function listRepaymentsForLoan(loanId: string): Promise<LoanRepayment[]> {
  return apiFetch<LoanRepayment[]>(`/api/loans/${loanId}/repayments`);
}

export async function listAllRepayments(status?: PaymentVerificationStatus): Promise<LoanRepayment[]> {
  return apiFetch<LoanRepayment[]>("/api/loan-repayments", { searchParams: { status } });
}

export async function getRepayment(id: string): Promise<LoanRepaymentWithReceipt> {
  return apiFetch<LoanRepaymentWithReceipt>(`/api/loan-repayments/${id}`);
}

export async function verifyRepayment(
  id: string,
  approved: boolean,
  rejectionReason?: string
): Promise<LoanRepayment> {
  return apiFetch<LoanRepayment>(`/api/loan-repayments/${id}/verify`, {
    method: "POST",
    body: { approved, rejection_reason: rejectionReason },
  });
}
