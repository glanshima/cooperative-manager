import { apiFetch } from "./client";

export type MemberStatus = "financial" | "non_financial";

// Mirrors the backend's AccountStatus enum (models.py) -- present here
// only for login_account_status below.
export type LoginAccountStatus = "active" | "deactivated" | "suspended";

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

// What a membership exit means financially. The backend REPORTS the
// savings offset (a member's savings is their accumulated monthly
// contribution) against the loans still outstanding; it never posts it,
// so applying the offset stays on the audited repayment flow.
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
