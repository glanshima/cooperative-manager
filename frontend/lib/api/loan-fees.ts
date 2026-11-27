import { apiFetch } from "./client";
import type { PaymentVerificationStatus } from "./applications";

// A direct loan's universal fee is cooperative income paid SEPARATELY from
// the loan: verifying one never changes the loan's payout, total or balance.
// Application-derived loans settle their fee during application review.
export interface LoanFeePayment {
  id: string;
  loan_id: string;
  member_id: string;
  amount: string;
  payment_reference: string;
  receipt_content_type: string;
  status: PaymentVerificationStatus;
  rejection_reason?: string | null;
  verified_at?: string | null;
  created_at: string;
  updated_at: string;
  // Visible to an officer who is conflicted against this member; actions
  // on it are refused (409).
  conflicted?: boolean;
}

export interface LoanFeePaymentWithReceipt extends LoanFeePayment {
  receipt_image_base64: string;
}

export interface LoanFeePaymentWithDetails extends LoanFeePayment {
  member_name: string;
  member_psn: string;
  loan_type_name: string;
}

export interface LoanFeePaymentInput {
  payment_reference: string;
  receipt_image_base64: string;
  receipt_content_type: string;
}

export async function submitFeePayment(
  loanId: string,
  input: LoanFeePaymentInput
): Promise<LoanFeePayment> {
  return apiFetch<LoanFeePayment>(`/api/loans/${loanId}/fee-payment`, {
    method: "POST",
    body: input,
  });
}

export async function listFeePaymentsForLoan(loanId: string): Promise<LoanFeePayment[]> {
  return apiFetch<LoanFeePayment[]>(`/api/loans/${loanId}/fee-payments`);
}

export async function listAllFeePayments(
  status?: PaymentVerificationStatus
): Promise<LoanFeePaymentWithDetails[]> {
  return apiFetch<LoanFeePaymentWithDetails[]>("/api/loan-fees", { searchParams: { status } });
}

export async function getFeePaymentReceipt(id: string): Promise<LoanFeePaymentWithReceipt> {
  return apiFetch<LoanFeePaymentWithReceipt>(`/api/loan-fees/${id}/receipt`);
}

export async function verifyFeePayment(
  id: string,
  approved: boolean,
  rejectionReason?: string
): Promise<LoanFeePayment> {
  return apiFetch<LoanFeePayment>(`/api/loan-fees/${id}/verify`, {
    method: "POST",
    body: { approved, rejection_reason: rejectionReason },
  });
}
