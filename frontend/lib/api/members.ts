import { apiFetch } from "./client";

export type MemberStatus = "financial" | "non_financial";

// Mirrors the backend's AccountStatus enum (models.py) -- present here
// only for login_account_status below.
export type LoginAccountStatus = "active" | "deactivated" | "suspended";

export interface Member {
  id: string;
  psn: string;
  // The printed form: "Last, First Other(s)".
  name: string;
  first_name?: string | null;
  last_name?: string | null;
  other_names?: string | null;
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
  // The agreed monthly savings contribution payroll deducts. Null until an
  // officer bootstraps it; from then on it only moves through an approved
  // contribution change request. contribution_effective_from is the first
  // payroll month the stored figure applies to (server-set).
  monthly_contribution_amount?: string | null;
  contribution_effective_from?: string | null;
  // Membership exit (see POST /api/members/{id}/withdraw). A non-null
  // exit date means the member formally LEFT the cooperative, which is
  // different from `non_financial` alone -- that also covers a member who
  // simply fell behind on contributions.
  membership_exit_date?: string | null;
  membership_exit_reason?: string | null;
  created_at: string;
  updated_at: string;
  // Login State Reconciliation Addendum: authoritative, backend-computed
  // login state. login_account_status is null/undefined when no login
  // exists yet -- that (and ONLY that) is what should drive showing
  // "Create Login" in the Members table. Never infer login existence
  // from any other field.
  login_user_id?: string | null;
  login_account_status?: LoginAccountStatus | null;
  // Member Relationship / Next-of-Kin Controlled Remediation (2026-09):
  // backend-computed, never inferred client-side. null means this
  // member has never had the question answered (a legacy record from
  // before this remediation, not auto-converted -- see the Phase 1
  // report). See schemas.py's MemberOut docstring.
  next_of_kin_is_member?: boolean | null;
  next_of_kin_member?: { id: string; psn: string; name: string; phone?: string | null } | null;
  // True when this member is linked to the signed-in officer by an active
  // conflict-of-interest relationship: the record stays visible, but every
  // action on it is refused (409) until another officer acts.
  conflicted?: boolean;
}

export interface MemberInput {
  psn: string;
  // The form sends the name in parts; the backend composes `name`. `name`
  // is only sent by legacy callers and is omitted by this app.
  first_name?: string;
  last_name?: string;
  other_names?: string;
  name?: string;
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
  // Bootstrap only: an officer records the initial figure here while it is
  // still unset. Once on file the backend refuses a direct edit (409) or a
  // clear (422) -- later changes go through a contribution change request.
  // Omit entirely on edits that aren't bootstrapping (see useMembersPage).
  monthly_contribution_amount?: number | null;
  // Member Relationship / Next-of-Kin Controlled Remediation (2026-09):
  // required on create (backend rejects a missing value with a 422 --
  // see schemas.py's MemberCreate docstring); when true,
  // next_of_kin_member_id is required and the manual next_of_kin*
  // fields above should be left blank. On update, `undefined` (the
  // field simply omitted from the request body) means "don't touch the
  // existing Next-of-Kin relationship" -- see updateMember below and
  // schemas.py's MemberUpdate docstring.
  next_of_kin_is_member?: boolean;
  next_of_kin_member_id?: string;
}

export interface MemberListResult {
  items: Member[];
  total: number;
  skip: number;
  limit: number;
}

export interface MemberFilterOptions {
  banks: string[];
  departments: string[];
}

// What a membership exit means financially, at the moment the exit is
// recorded. Applying the savings offset is a separate, deliberate step
// (settleMemberExit below), run once the member's final payroll month is
// confirmed -- recording the exit never moves money.
export interface MemberWithdrawal {
  member: Member;
  savings_balance: string;
  active_loan_count: number;
  active_loan_outstanding: string;
  payroll_recovery_still_due: string;
}

export interface MemberListParams {
  search?: string;
  bank_name?: string;
  department?: string;
  status?: MemberStatus;
  settlement?: SettlementPayoutStatus;
  skip?: number;
  limit?: number;
}

export async function listMembers(params: MemberListParams = {}): Promise<MemberListResult> {
  return apiFetch<MemberListResult>("/api/members", {
    searchParams: {
      search: params.search || undefined,
      bank_name: params.bank_name || undefined,
      department: params.department || undefined,
      status: params.status || undefined,
      settlement: params.settlement || undefined,
      skip: params.skip !== undefined ? String(params.skip) : undefined,
      limit: params.limit !== undefined ? String(params.limit) : undefined,
    },
  });
}

export async function getMemberFilterOptions(): Promise<MemberFilterOptions> {
  return apiFetch<MemberFilterOptions>("/api/members/filter-options");
}

export async function getMyMemberRecord(): Promise<Member> {
  return apiFetch<Member>("/api/members/me");
}

export type MemberDeductionStatus = "draft" | "submitted" | "confirmed" | "not_deducted";

/**
 * The member's own payroll deduction for one month. Contribution and loan
 * lines are separate on purpose: the figure payroll held back for savings is
 * not the figure it held back for loans. `status` says whether the money
 * actually left the paycheck -- draft and submitted are intent.
 */
export interface MemberDeductions {
  month: string;
  status: MemberDeductionStatus | null;
  contribution: string;
  loan_repayment: string;
  other: string;
  total: string;
}

export async function getMyDeductions(month?: string): Promise<MemberDeductions> {
  return apiFetch<MemberDeductions>("/api/members/me/deductions", {
    searchParams: month ? { month } : undefined,
  });
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

export async function updateMemberLoginStatus(
  id: string,
  accountStatus: LoginAccountStatus,
  reason?: string
): Promise<Member> {
  return apiFetch<Member>(`/api/members/${id}/login-status`, {
    method: "PATCH",
    body: { account_status: accountStatus, reason: reason ?? null },
  });
}

export async function withdrawMember(
  id: string,
  reason: string,
  exitDate?: string
): Promise<MemberWithdrawal> {
  return apiFetch<MemberWithdrawal>(`/api/members/${id}/withdraw`, {
    method: "POST",
    body: { reason, exit_date: exitDate ?? null },
  });
}

export type SettlementPayoutStatus = "pending" | "paid";

// Which account the payout left from. When the cashbook is open this decides
// the journal entry (payout payable -> cash or bank).
export type SettlementPaymentMethod = "cash" | "bank";

export interface SettlementAllocation {
  loan_id: string;
  amount: string;
  loan_type_name?: string | null;
}

// What was settled, as a snapshot taken at exit settlement. The payout is
// a recorded claim on the office until it is marked paid; the savings
// ledger was already debited when the settlement was created.
export interface MemberSettlement {
  id: string;
  member_id: string;
  settled_on: string;
  settled_at?: string | null;
  savings_balance: string;
  offset_total: string;
  payout_amount: string;
  payout_status: SettlementPayoutStatus;
  paid_on?: string | null;
  paid_at?: string | null;
  paid_reference?: string | null;
  paid_from?: SettlementPaymentMethod | null;
  note?: string | null;
  allocations: SettlementAllocation[];
}

export interface MemberSettlementPreview {
  member_id: string;
  savings_balance: string;
  active_loan_count: number;
  active_loan_outstanding: string;
  settlement: MemberSettlement | null;
}

export async function getMemberSettlement(id: string): Promise<MemberSettlementPreview> {
  return apiFetch<MemberSettlementPreview>(`/api/members/${id}/settlement`);
}

export async function settleMemberExit(
  id: string,
  input: { settled_on?: string; note?: string } = {}
): Promise<MemberSettlement> {
  return apiFetch<MemberSettlement>(`/api/members/${id}/settle-exit`, {
    method: "POST",
    body: { settled_on: input.settled_on ?? null, note: input.note ?? null },
  });
}

export async function markSettlementPaid(
  id: string,
  input: { paid_on?: string; reference: string; paid_from: SettlementPaymentMethod; note?: string }
): Promise<MemberSettlement> {
  return apiFetch<MemberSettlement>(`/api/members/${id}/settlements/mark-paid`, {
    method: "POST",
    body: {
      paid_on: input.paid_on ?? null,
      reference: input.reference,
      paid_from: input.paid_from,
      note: input.note ?? null,
    },
  });
}
