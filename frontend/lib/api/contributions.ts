import { apiFetch } from "./client";

export type ContributionChangeRequestStatus = "pending" | "approved" | "rejected";

export interface ContributionChangeRequest {
  id: string;
  member_id: string;
  member_name: string | null;
  member_psn: string | null;
  current_amount: string | null;
  requested_amount: string;
  reason: string | null;
  status: ContributionChangeRequestStatus;
  effective_from: string | null;
  requested_by_user_id: string | null;
  reviewed_by_user_id: string | null;
  reviewed_at: string | null;
  review_reason: string | null;
  created_at: string;
  updated_at: string;
  conflicted: boolean;
}

export interface ContributionChangeRequestCreateInput {
  requested_amount: number;
  reason: string;
}

export interface ContributionChangeRequestOnBehalfInput extends ContributionChangeRequestCreateInput {
  member_id: string;
}

export interface ContributionChangeReviewInput {
  reason?: string;
}

// --- Member self-service (powers the member dashboard) ---

export async function createContributionChangeRequest(
  input: ContributionChangeRequestCreateInput
): Promise<ContributionChangeRequest> {
  return apiFetch<ContributionChangeRequest>(
    "/api/members/me/contribution-change-requests",
    { method: "POST", body: input }
  );
}

export async function getMyContributionChangeRequests(): Promise<ContributionChangeRequest[]> {
  return apiFetch<ContributionChangeRequest[]>("/api/members/me/contribution-change-requests");
}

// --- Officer review (powers the admin Members page) ---

export async function listContributionChangeRequests(params: {
  status?: ContributionChangeRequestStatus;
  member_id?: string;
} = {}): Promise<ContributionChangeRequest[]> {
  return apiFetch<ContributionChangeRequest[]>("/api/contribution-change-requests", {
    searchParams: { status: params.status, member_id: params.member_id },
  });
}

export async function createContributionChangeRequestOnBehalf(
  input: ContributionChangeRequestOnBehalfInput
): Promise<ContributionChangeRequest> {
  return apiFetch<ContributionChangeRequest>("/api/contribution-change-requests", {
    method: "POST",
    body: input,
  });
}

export async function approveContributionChangeRequest(
  id: string,
  input: ContributionChangeReviewInput = {}
): Promise<ContributionChangeRequest> {
  return apiFetch<ContributionChangeRequest>(`/api/contribution-change-requests/${id}/approve`, {
    method: "POST",
    body: input,
  });
}

export async function rejectContributionChangeRequest(
  id: string,
  input: ContributionChangeReviewInput
): Promise<ContributionChangeRequest> {
  return apiFetch<ContributionChangeRequest>(`/api/contribution-change-requests/${id}/reject`, {
    method: "POST",
    body: input,
  });
}