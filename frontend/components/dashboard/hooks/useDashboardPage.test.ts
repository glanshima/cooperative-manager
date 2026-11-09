import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  fileToBase64,
  getMyMemberRecord,
  getSettings,
  listLoanApplications,
  listLoans,
  listLoanTypes,
  submitRepayment,
} from "@/lib/api";
import type { CurrentUser, Loan, Settings } from "@/lib/api";

import { useDashboardPage } from "./useDashboardPage";

vi.mock("@/lib/api", () => ({
  getMyMemberRecord: vi.fn(),
  getSettings: vi.fn(),
  listLoanApplications: vi.fn(),
  listLoans: vi.fn(),
  listLoanTypes: vi.fn(),
  submitLoanApplication: vi.fn(),
  fileToBase64: vi.fn(),
  submitRepayment: vi.fn(),
  cancelApplication: vi.fn(),
  rescheduleApplication: vi.fn(),
  reapplyLoanApplication: vi.fn(),
}));

const getMyMemberRecordMock = vi.mocked(getMyMemberRecord);
const getSettingsMock = vi.mocked(getSettings);
const listLoanApplicationsMock = vi.mocked(listLoanApplications);
const listLoansMock = vi.mocked(listLoans);
const listLoanTypesMock = vi.mocked(listLoanTypes);
const fileToBase64Mock = vi.mocked(fileToBase64);
const submitRepaymentMock = vi.mocked(submitRepayment);

const user: CurrentUser = {
  id: "user-1",
  username: "MCT-0001",
  role: "member",
  member_id: "member-1",
  must_change_password: false,
  is_active: true,
  account_status: "active",
  is_super_admin: false,
  last_login_at: null,
  created_at: "2026-11-01T00:00:00Z",
};

const settings: Settings = {
  id: "settings-1",
  loan_restriction_behavior: "block",
  loan_form_fee: "50.00",
  members_module_enabled: true,
  loans_module_enabled: true,
  deductions_module_enabled: true,
  cashbook_module_enabled: true,
  dividends_module_enabled: true,
};

const logout = vi.fn();

describe("useDashboardPage module gating", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    getMyMemberRecordMock.mockResolvedValue({ id: "member-1" } as any);
    getSettingsMock.mockResolvedValue(settings);
    listLoanApplicationsMock.mockResolvedValue([]);
    listLoansMock.mockResolvedValue([]);
    listLoanTypesMock.mockResolvedValue([]);
  });

  it("loads loan data when the Loans module is enabled", async () => {
    const { result } = renderHook(() => useDashboardPage(false, user, logout));

    await waitFor(() => expect(result.current.loading).toBe(false));

    expect(listLoanApplicationsMock).toHaveBeenCalledTimes(1);
    expect(listLoansMock).toHaveBeenCalledTimes(1);
    expect(listLoanTypesMock).toHaveBeenCalledTimes(1);
    expect(result.current.loansEnabled).toBe(true);
  });

  it("skips every loan request when the Loans module is disabled", async () => {
    getSettingsMock.mockResolvedValue({ ...settings, loans_module_enabled: false });

    const { result } = renderHook(() => useDashboardPage(false, user, logout));

    await waitFor(() => expect(result.current.loading).toBe(false));

    expect(listLoanApplicationsMock).not.toHaveBeenCalled();
    expect(listLoansMock).not.toHaveBeenCalled();
    expect(listLoanTypesMock).not.toHaveBeenCalled();
    expect(result.current.loansEnabled).toBe(false);
    expect(result.current.applications.items).toEqual([]);
    expect(result.current.loans.items).toEqual([]);
    expect(result.current.apply.applyableTypes).toEqual([]);
    expect(result.current.feedback.error).toBeNull();
  });
});

describe("useDashboardPage repayments", () => {
  const loan = {
    id: "loan-1",
    monthly_installment: "12000.00",
    status: "active",
  } as Loan;

  beforeEach(() => {
    vi.clearAllMocks();
    getMyMemberRecordMock.mockResolvedValue({ id: "member-1" } as any);
    getSettingsMock.mockResolvedValue(settings);
    listLoanApplicationsMock.mockResolvedValue([]);
    listLoansMock.mockResolvedValue([loan]);
    listLoanTypesMock.mockResolvedValue([]);
    fileToBase64Mock.mockResolvedValue("cmVjZWlwdA==");
    submitRepaymentMock.mockResolvedValue({} as any);
  });

  it("sends the month the member says they paid, not today's month", async () => {
    const { result } = renderHook(() => useDashboardPage(false, user, logout));
    await waitFor(() => expect(result.current.loading).toBe(false));

    act(() => result.current.loans.startRepayment(loan));
    expect(result.current.loans.repayAmount).toBe(12000);

    act(() => {
      result.current.loans.setRepayMonth("2026-09");
      result.current.loans.setRepayReference("TRF-9");
      result.current.loans.setRepayReceiptFile(
        new File(["receipt"], "receipt.png", { type: "image/png" })
      );
    });

    await act(async () => {
      await result.current.loans.submitRepayment({ preventDefault: () => {} } as any);
    });

    expect(submitRepaymentMock).toHaveBeenCalledWith("loan-1", {
      amount_claimed: 12000,
      payment_month: "2026-09",
      payment_reference: "TRF-9",
      receipt_image_base64: "cmVjZWlwdA==",
      receipt_content_type: "image/png",
    });
  });

  it("refuses to submit without a payment month", async () => {
    const { result } = renderHook(() => useDashboardPage(false, user, logout));
    await waitFor(() => expect(result.current.loading).toBe(false));

    act(() => result.current.loans.startRepayment(loan));
    act(() => {
      result.current.loans.setRepayMonth("");
      result.current.loans.setRepayReceiptFile(
        new File(["receipt"], "receipt.png", { type: "image/png" })
      );
    });

    await act(async () => {
      await result.current.loans.submitRepayment({ preventDefault: () => {} } as any);
    });

    expect(submitRepaymentMock).not.toHaveBeenCalled();
    expect(result.current.feedback.error).toBe("Choose the month this payment covers.");
  });
});
