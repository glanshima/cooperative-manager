import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  decideApplication,
  disburseApplication,
  getLoanApplication,
  listLoanApplications,
  verifyPayment,
} from "@/lib/api";
import type { LoanApplication, LoanApplicationWithReceipt } from "@/lib/api";

import { useLoanApplicationsPage } from "./useLoanApplicationsPage";

vi.mock("@/lib/api", () => ({
  listLoanApplications: vi.fn(),
  getLoanApplication: vi.fn(),
  verifyPayment: vi.fn(),
  decideApplication: vi.fn(),
  disburseApplication: vi.fn(),
}));

const listMock = vi.mocked(listLoanApplications);
const getMock = vi.mocked(getLoanApplication);
const verifyMock = vi.mocked(verifyPayment);
const decideMock = vi.mocked(decideApplication);
const disburseMock = vi.mocked(disburseApplication);

const summary = {
  id: "app-1",
  member_id: "member-1",
  member_name: "Ada Obi",
  member_psn: "MCT-0001",
  loan_type_name: "Capital Loan",
  requested_amount: "100000.00",
  requested_tenure_months: 12,
  payment_status: "awaiting_verification",
  status: "pending",
  was_restricted_at_submission: false,
} as unknown as LoanApplication;

const full = {
  ...summary,
  payment_reference: "REF-001",
  preferred_disbursement_date: "2026-12-01",
  use_default_account: true,
  receipt_content_type: "image/png",
  receipt_image_base64: "abc",
} as unknown as LoanApplicationWithReceipt;

const logout = vi.fn();

async function renderLoadedHook() {
  const rendered = renderHook(() => useLoanApplicationsPage(false, logout));
  await waitFor(() => expect(rendered.result.current.loading).toBe(false));
  return rendered;
}

async function expandApplication(result: Awaited<ReturnType<typeof renderLoadedHook>>["result"]) {
  await act(async () => {
    await result.current.table.onReview("app-1");
  });
}

describe("useLoanApplicationsPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    listMock.mockResolvedValue([summary]);
    getMock.mockResolvedValue(full);
    verifyMock.mockResolvedValue(summary);
    decideMock.mockResolvedValue(summary);
    disburseMock.mockResolvedValue(summary);
  });

  it("loads the application list and seeds the review form on expand", async () => {
    const { result } = await renderLoadedHook();

    expect(result.current.table.items).toEqual([summary]);

    await expandApplication(result);

    expect(getMock).toHaveBeenCalledWith("app-1");
    expect(result.current.review.application).toEqual(full);
    expect(result.current.review.form.approvedAmount).toBe("100000.00");
    expect(result.current.review.form.approvedTenureMonths).toBe("12");
    expect(result.current.review.form.rejectionReason).toBe("");
  });

  it("passes the rejection reason when payment verification fails", async () => {
    const { result } = await renderLoadedHook();
    await expandApplication(result);

    act(() => {
      result.current.review.form.setRejectionReason("Receipt is unreadable");
    });

    await act(async () => {
      await result.current.review.onVerifyPayment(false);
    });

    expect(verifyMock).toHaveBeenCalledWith("app-1", false, "Receipt is unreadable");
    expect(result.current.review.application).toBeNull();
    expect(listMock).toHaveBeenCalledTimes(2);
  });

  it("sends parsed numeric values and the reapply flag on approval", async () => {
    const { result } = await renderLoadedHook();
    await expandApplication(result);

    act(() => {
      result.current.review.form.setApprovedAmount("50000");
      result.current.review.form.setApprovedTenureMonths("10");
      result.current.review.form.setTenureDecisionReason("Shorter tenure agreed");
      result.current.review.form.setAdminNotes("Approved");
      result.current.review.form.setCanReapply(false);
    });

    await act(async () => {
      await result.current.review.onDecide(true);
    });

    expect(decideMock).toHaveBeenCalledWith(
      "app-1",
      true,
      50000,
      10,
      "Shorter tenure agreed",
      "Approved",
      false
    );
    expect(result.current.review.application).toBeNull();
  });

  it("does not disburse when the confirmation is dismissed", async () => {
    const { result } = await renderLoadedHook();
    await expandApplication(result);

    vi.stubGlobal("confirm", vi.fn(() => false));
    await act(async () => {
      await result.current.review.onDisburse("app-1");
    });

    expect(disburseMock).not.toHaveBeenCalled();
    expect(result.current.review.application).toEqual(full);

    vi.stubGlobal("confirm", vi.fn(() => true));
    await act(async () => {
      await result.current.review.onDisburse("app-1");
    });

    expect(disburseMock).toHaveBeenCalledWith("app-1");
  });
});
