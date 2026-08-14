const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

// ---------------------------------------------------------------------------
// Auth token handling
// ---------------------------------------------------------------------------

const TOKEN_KEY = "mact_access_token";

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string) {
  localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken() {
  localStorage.removeItem(TOKEN_KEY);
}

async function handle<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || `Request failed with status ${res.status}`);
  }
  if (res.status === 204) return undefined as unknown as T;
  return res.json();
}

/**
 * Shared fetch wrapper: attaches the Authorization header when a token is
 * present, sets Content-Type for JSON bodies, and never caches (all our
 * data is mutable and small-scale, so freshness matters more than speed).
 */
async function apiFetch<T>(
  path: string,
  options: { method?: string; body?: unknown; searchParams?: Record<string, string | undefined> } = {}
): Promise<T> {
  const url = new URL(`${API_URL}${path}`);
  if (options.searchParams) {
    for (const [key, value] of Object.entries(options.searchParams)) {
      if (value !== undefined) url.searchParams.set(key, value);
    }
  }

  const token = getToken();
  const headers: Record<string, string> = {};
  if (token) headers["Authorization"] = `Bearer ${token}`;
  if (options.body !== undefined) headers["Content-Type"] = "application/json";

  const res = await fetch(url.toString(), {
    method: options.method || "GET",
    headers,
    body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
    cache: "no-store",
  });
  return handle<T>(res);
}

// ---------------------------------------------------------------------------
// Auth
// ---------------------------------------------------------------------------

export type UserRole = "admin" | "member";

export interface LoginResponse {
  access_token: string;
  token_type: string;
  role: UserRole;
  must_change_password: boolean;
}

export interface CurrentUser {
  id: string;
  username: string;
  role: UserRole;
  member_id?: string | null;
  must_change_password: boolean;
  is_active: boolean;
  created_at: string;
}

export async function login(username: string, password: string): Promise<LoginResponse> {
  const result = await apiFetch<LoginResponse>("/api/auth/login", {
    method: "POST",
    body: { username, password },
  });
  setToken(result.access_token);
  return result;
}

export function logout() {
  clearToken();
}

export async function getMe(): Promise<CurrentUser> {
  return apiFetch<CurrentUser>("/api/auth/me");
}

export async function changePassword(currentPassword: string, newPassword: string): Promise<CurrentUser> {
  return apiFetch<CurrentUser>("/api/auth/change-password", {
    method: "POST",
    body: { current_password: currentPassword, new_password: newPassword },
  });
}

export async function createMemberLogin(memberId: string, temporaryPassword: string): Promise<CurrentUser> {
  return apiFetch<CurrentUser>("/api/auth/create-member-login", {
    method: "POST",
    body: { member_id: memberId, temporary_password: temporaryPassword },
  });
}

export async function resetMemberPassword(memberId: string, temporaryPassword: string): Promise<CurrentUser> {
  return apiFetch<CurrentUser>("/api/auth/reset-member-password", {
    method: "POST",
    body: { member_id: memberId, temporary_password: temporaryPassword },
  });
}

// ---------------------------------------------------------------------------
// Members
// ---------------------------------------------------------------------------

export type MemberStatus = "financial" | "non_financial";

export interface Member {
  id: string;
  psn: string;
  name: string;
  bank_name?: string | null;
  account_number?: string | null;
  gender?: string | null;
  department?: string | null;
  phone?: string | null;
  email?: string | null;
  next_of_kin?: string | null;
  next_of_kin_phone?: string | null;
  next_of_kin_address?: string | null;
  next_of_kin_email?: string | null;
  next_of_kin_relationship?: string | null;
  status: MemberStatus;
  loan_restricted: boolean;
  restriction_reason?: string | null;
  created_at: string;
  updated_at: string;
}

export interface MemberInput {
  psn: string;
  name: string;
  bank_name?: string;
  account_number?: string;
  gender?: string;
  department?: string;
  phone?: string;
  email?: string;
  next_of_kin?: string;
  next_of_kin_phone?: string;
  next_of_kin_address?: string;
  next_of_kin_email?: string;
  next_of_kin_relationship?: string;
  status: MemberStatus;
  loan_restricted?: boolean;
  restriction_reason?: string;
}

export async function listMembers(search?: string): Promise<Member[]> {
  return apiFetch<Member[]>("/api/members", { searchParams: { search } });
}

export async function getMyMemberRecord(): Promise<Member> {
  return apiFetch<Member>("/api/members/me");
}

export async function createMember(input: MemberInput): Promise<Member> {
  return apiFetch<Member>("/api/members", { method: "POST", body: input });
}

export async function updateMember(id: string, input: Partial<MemberInput>): Promise<Member> {
  return apiFetch<Member>(`/api/members/${id}`, { method: "PUT", body: input });
}

export async function deleteMember(id: string): Promise<void> {
  return apiFetch<void>(`/api/members/${id}`, { method: "DELETE" });
}

// ---------------------------------------------------------------------------
// Loan Types
// ---------------------------------------------------------------------------

export interface LoanType {
  id: string;
  name: string;
  interest_rate: string; // decimal fraction as string, e.g. "0.1500" - current effective rate (cached)
  tenure_months: number;
  flat_charge: string;
  is_active: boolean;
  open_for_application: boolean;
  created_at: string;
  updated_at: string;
}

export interface LoanTypeCreateInput {
  name: string;
  interest_rate: number;
  tenure_months: number;
  flat_charge?: number;
  is_active?: boolean;
  open_for_application?: boolean;
  effective_from?: string; // ISO date; defaults to today if omitted
}

export interface LoanTypeUpdateInput {
  name?: string;
  is_active?: boolean;
  open_for_application?: boolean;
}

export interface LoanTypeRateVersion {
  id: string;
  loan_type_id: string;
  interest_rate: string;
  tenure_months: number;
  flat_charge: string;
  effective_from: string;
  created_at: string;
}

export interface LoanTypeRateVersionInput {
  interest_rate: number;
  tenure_months: number;
  flat_charge?: number;
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

// ---------------------------------------------------------------------------
// Loans
// ---------------------------------------------------------------------------

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
  disbursement_date: string;
  expected_end_date: string;
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

// ---------------------------------------------------------------------------
// Loan Applications
// ---------------------------------------------------------------------------

export type LoanApplicationStatus = "pending" | "approved" | "rejected";
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
  member_name: string;
  member_psn: string;
  loan_type_name: string;
  created_at: string;
  updated_at: string;
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
  alternate_account_number?: string;
  member_notes?: string;
  payment_reference: string;
  receipt_image_base64: string;
  receipt_content_type: string;
}

export async function listLoanApplications(params?: {
  status?: LoanApplicationStatus;
  payment_status?: PaymentVerificationStatus;
}): Promise<LoanApplication[]> {
  return apiFetch<LoanApplication[]>("/api/loan-applications", { searchParams: params });
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
  adminNotes?: string
): Promise<LoanApplication> {
  return apiFetch<LoanApplication>(`/api/loan-applications/${id}/decide`, {
    method: "POST",
    body: {
      approved,
      approved_amount: approvedAmount,
      approved_tenure_months: approvedTenureMonths,
      tenure_decision_reason: tenureDecisionReason,
      admin_notes: adminNotes,
    },
  });
}

export async function disburseApplication(id: string): Promise<LoanApplication> {
  return apiFetch<LoanApplication>(`/api/loan-applications/${id}/disburse`, {
    method: "POST",
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

// ---------------------------------------------------------------------------
// Loan Repayments (servicing an active loan)
// ---------------------------------------------------------------------------

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

// ---------------------------------------------------------------------------
// Settings
// ---------------------------------------------------------------------------

export type LoanRestrictionBehavior = "block" | "warn";

export interface Settings {
  id: string;
  loan_restriction_behavior: LoanRestrictionBehavior;
  loan_form_fee: string;
  members_module_enabled: boolean;
  loans_module_enabled: boolean;
  deductions_module_enabled: boolean;
  cashbook_module_enabled: boolean;
  dividends_module_enabled: boolean;
}

export async function getSettings(): Promise<Settings> {
  return apiFetch<Settings>("/api/settings");
}

export async function updateSettings(input: Partial<Settings>): Promise<Settings> {
  return apiFetch<Settings>("/api/settings", { method: "PUT", body: input });
}
