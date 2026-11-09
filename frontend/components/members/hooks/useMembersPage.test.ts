import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  getMemberFilterOptions,
  listMembers,
  updateMember,
  withdrawMember,
} from "@/lib/api";
import type { Member, MemberListResult, MemberWithdrawal } from "@/lib/api";
import {
  approveContributionChangeRequest,
  listContributionChangeRequests,
  rejectContributionChangeRequest,
} from "@/lib/api/contributions";
import type { ContributionChangeRequest } from "@/lib/api/contributions";

import { useMembersPage } from "./useMembersPage";

vi.mock("@/lib/api", () => ({
  // members/utils.ts's describeError() tests `e instanceof ApiError`, so
  // the module mock has to expose the class even though nothing here
  // throws one.
  ApiError: class ApiError extends Error {},
  listMembers: vi.fn(),
  getMemberFilterOptions: vi.fn(),
  createMember: vi.fn(),
  updateMember: vi.fn(),
  deleteMember: vi.fn(),
  createMemberLogin: vi.fn(),
  updateMemberLoginStatus: vi.fn(),
  withdrawMember: vi.fn(),
}));

vi.mock("@/lib/api/contributions", () => ({
  listContributionChangeRequests: vi.fn(),
  approveContributionChangeRequest: vi.fn(),
  rejectContributionChangeRequest: vi.fn(),
}));

const listMock = vi.mocked(listMembers);
const filterMock = vi.mocked(getMemberFilterOptions);
const withdrawMock = vi.mocked(withdrawMember);
const updateMock = vi.mocked(updateMember);
const contribListMock = vi.mocked(listContributionChangeRequests);
const contribApproveMock = vi.mocked(approveContributionChangeRequest);
const contribRejectMock = vi.mocked(rejectContributionChangeRequest);

const logout = vi.fn();

const activeMember = {
  id: "member-1",
  psn: "MCT-0001",
  name: "Ada Obi",
  status: "financial",
  loan_restricted: false,
  membership_exit_date: null,
  login_account_status: "active",
} as unknown as Member;

const exitedMember = {
  ...activeMember,
  id: "member-2",
  psn: "MCT-0002",
  name: "Bee Kule",
  status: "non_financial",
  membership_exit_date: "2026-09-30",
} as unknown as Member;

const withdrawal = {
  member: { ...activeMember, status: "non_financial" },
  savings_balance: "6000.00",
  active_loan_count: 1,
  active_loan_outstanding: "7000.00",
  payroll_recovery_still_due: "1000.00",
} as unknown as MemberWithdrawal;

async function renderLoadedHook() {
  const rendered = renderHook(() => useMembersPage(false, logout));
  await waitFor(() => expect(rendered.result.current.table.loading).toBe(false));
  return rendered;
}

describe("useMembersPage membership exit", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    listMock.mockResolvedValue({
      items: [activeMember, exitedMember],
      total: 2,
      skip: 0,
      limit: 25,
    } as MemberListResult);
    filterMock.mockResolvedValue({ banks: [], departments: [] });
    contribListMock.mockResolvedValue([]);
  });

  it("records the exit and reports what payroll still has to recover", async () => {
    withdrawMock.mockResolvedValue(withdrawal);
    const promptMock = vi.spyOn(window, "prompt").mockReturnValue("Member applied to withdraw");
    const rendered = await renderLoadedHook();

    await act(async () => {
      await rendered.result.current.table.onWithdraw(activeMember);
    });

    expect(withdrawMock).toHaveBeenCalledWith("member-1", "Member applied to withdraw");
    expect(rendered.result.current.feedback.error).toBeNull();
    expect(rendered.result.current.feedback.success).toContain("1000.00");
    expect(rendered.result.current.feedback.success).toContain("exited");
    promptMock.mockRestore();
  });

  it("sends nothing when the officer dismisses the prompt", async () => {
    vi.spyOn(window, "prompt").mockReturnValue(null);
    const rendered = await renderLoadedHook();

    await act(async () => {
      await rendered.result.current.table.onWithdraw(activeMember);
    });

    expect(withdrawMock).not.toHaveBeenCalled();
    expect(rendered.result.current.feedback.success).toBeNull();
  });

  it("surfaces a refusal from the backend", async () => {
    withdrawMock.mockRejectedValue(new Error("You cannot record this member's exit"));
    vi.spyOn(window, "prompt").mockReturnValue("Reason");
    const rendered = await renderLoadedHook();

    await act(async () => {
      await rendered.result.current.table.onWithdraw(activeMember);
    });

    expect(rendered.result.current.feedback.error).toContain("cannot record");
    expect(rendered.result.current.feedback.success).toBeNull();
  });
});

const pendingRequest = {
  id: "req-1",
  member_id: "member-1",
  member_name: "Ada Obi",
  member_psn: "MCT-0001",
  current_amount: "5000.00",
  requested_amount: "8000.00",
  reason: "Salary increase",
  status: "pending",
  effective_from: null,
  requested_by_user_id: "user-9",
  reviewed_by_user_id: null,
  reviewed_at: null,
  review_reason: null,
  created_at: "2026-11-01T00:00:00Z",
  updated_at: "2026-11-01T00:00:00Z",
  conflicted: false,
} as ContributionChangeRequest;

const contributingMember = {
  ...activeMember,
  id: "member-3",
  monthly_contribution_amount: "5000.00",
} as unknown as Member;

describe("useMembersPage contributions", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    listMock.mockResolvedValue({
      items: [activeMember, exitedMember],
      total: 2,
      skip: 0,
      limit: 25,
    } as MemberListResult);
    filterMock.mockResolvedValue({ banks: [], departments: [] });
    contribListMock.mockResolvedValue([]);
    updateMock.mockResolvedValue(activeMember);
  });

  it("loads the officer review queue on mount", async () => {
    contribListMock.mockResolvedValue([pendingRequest]);
    const rendered = await renderLoadedHook();

    await waitFor(() => expect(rendered.result.current.contributions.available).toBe(true));
    expect(contribListMock).toHaveBeenCalled();
    expect(rendered.result.current.contributions.requests).toHaveLength(1);
  });

  it("hides the panel when the queue is refused (officer lacks savings.view)", async () => {
    contribListMock.mockRejectedValue(new Error("Request failed with status 403"));
    const rendered = await renderLoadedHook();

    await waitFor(() => expect(rendered.result.current.table.loading).toBe(false));
    expect(rendered.result.current.contributions.available).toBe(false);
  });

  it("approves a pending request and reports success", async () => {
    contribListMock.mockResolvedValue([pendingRequest]);
    contribApproveMock.mockResolvedValue({ ...pendingRequest, status: "approved" });
    const rendered = await renderLoadedHook();
    await waitFor(() => expect(rendered.result.current.contributions.available).toBe(true));

    await act(async () => {
      await rendered.result.current.contributions.approve("req-1", "Looks reasonable");
    });

    expect(contribApproveMock).toHaveBeenCalledWith("req-1", { reason: "Looks reasonable" });
    expect(rendered.result.current.feedback.success).toContain("approved");
    expect(rendered.result.current.feedback.error).toBeNull();
  });

  it("rejects a pending request with the reason supplied", async () => {
    contribListMock.mockResolvedValue([pendingRequest]);
    contribRejectMock.mockResolvedValue({ ...pendingRequest, status: "rejected" });
    const rendered = await renderLoadedHook();
    await waitFor(() => expect(rendered.result.current.contributions.available).toBe(true));

    await act(async () => {
      await rendered.result.current.contributions.reject("req-1", "Above the agreed cap");
    });

    expect(contribRejectMock).toHaveBeenCalledWith("req-1", { reason: "Above the agreed cap" });
    expect(rendered.result.current.feedback.success).toContain("rejected");
  });

  it("omits the contribution on edits once it is already on file", async () => {
    const rendered = await renderLoadedHook();

    act(() => rendered.result.current.form.startEdit(contributingMember));
    expect(rendered.result.current.form.contributionLocked).toBe(true);

    await act(async () => {
      await rendered.result.current.form.submit({ preventDefault: () => {} } as any);
    });

    expect(updateMock).toHaveBeenCalledTimes(1);
    expect(updateMock.mock.calls[0][0]).toBe("member-3");
    expect(updateMock.mock.calls[0][1]).not.toHaveProperty("monthly_contribution_amount");
  });

  it("bootstraps a contribution for a member who has none yet", async () => {
    const rendered = await renderLoadedHook();

    act(() => rendered.result.current.form.startEdit(activeMember));
    expect(rendered.result.current.form.contributionLocked).toBe(false);
    act(() => rendered.result.current.form.setField("monthly_contribution_amount", 6000));

    await act(async () => {
      await rendered.result.current.form.submit({ preventDefault: () => {} } as any);
    });

    expect(updateMock).toHaveBeenCalledTimes(1);
    expect(updateMock.mock.calls[0][1]).toHaveProperty("monthly_contribution_amount", 6000);
  });
});
