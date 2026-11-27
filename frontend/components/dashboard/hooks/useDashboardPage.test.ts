import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  fileToBase64,
  getMemberLoanBalance,
  getMyDeductions,
  getMyMemberRecord,
  getMySavings,
  getNotifications,
  getSettings,
  listLoanApplications,
  listLoans,
  listLoanTypes,
  listRepaymentsForLoan,
  submitLoanApplication,
  submitRepayment,
} from "@/lib/api";
import type { CurrentUser, Loan, Settings } from "@/lib/api";

import { useDashboardPage } from "./useDashboardPage";

vi.mock("@/lib/api", () => ({
  getMyMemberRecord: vi.fn(),
  getMySavings: vi.fn(),
  getMyDeductions: vi.fn(),
  getMemberLoanBalance: vi.fn(),
  getNotifications: vi.fn(),
  getSettings: vi.fn(),
  listRepaymentsForLoan: vi.fn(),
  listLoanApplications: vi.fn(),
  listLoans: vi.fn(),
  listLoanTypes: vi.fn(),
  submitLoanApplication: vi.fn(),
  submitFeePayment: vi.fn(),
  fileToBase64: vi.fn(),
  submitRepayment: vi.fn(),
  cancelApplication: vi.fn(),
  rescheduleApplication: vi.fn(),
  reapplyLoanApplication: vi.fn(),
}));

const getMyMemberRecordMock = vi.mocked(getMyMemberRecord);
const getMySavingsMock = vi.mocked(getMySavings);
const getMyDeductionsMock = vi.mocked(getMyDeductions);
const getMemberLoanBalanceMock = vi.mocked(getMemberLoanBalance);
const getNotificationsMock = vi.mocked(getNotifications);
const getSettingsMock = vi.mocked(getSettings);
const listRepaymentsForLoanMock = vi.mocked(listRepaymentsForLoan);
const listLoanApplicationsMock = vi.mocked(listLoanApplications);
const listLoansMock = vi.mocked(listLoans);
const listLoanTypesMock = vi.mocked(listLoanTypes);
const submitLoanApplicationMock = vi.mocked(submitLoanApplication);
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
  permissions: [],
  last_login_at: null,
  created_at: "2026-11-01T00:00:00Z",
};

const settings: Settings = {
  id: "settings-1",
  loan_restriction_behavior: "block",
  loan_form_fee: "50.00",
  loan_interest_mode: "at_source",
  loan_interest_spread_months: null,
  minimum_monthly_contribution: "0.00",
  default_monthly_contribution: "0.00",
  loan_default_charge_pct: "0.00",
  loan_default_grace_mode: "next_payroll",
  loan_default_grace_days: 0,
  members_module_enabled: true,
  loans_module_enabled: true,
  deductions_module_enabled: true,
  cashbook_module_enabled: true,
  dividends_module_enabled: true,
  fiscal_year_start_month: 1,
  dividend_basis: "net_savings_closing",
  dividend_pool_mode: "net_income_share",
  dividend_reserve_pct: "4.70",
  dividend_honorarium_pct: "3.00",
  dividend_payout_pct: "92.30",
  dividend_declared_rate_pct: null,
  dividend_fixed_pool_amount: null,
  dividend_hybrid_savings_pct: "50.00",
  dividend_min_membership_months: 0,
  dividend_include_exited: false,
  dividend_rounding: "two_dp",
  dividend_withholding_pct: "0.00",
  dividend_payment_method: "bank",
  cooperative_name: "MACT Cooperative",
  cooperative_short_name: "MACT",
  cooperative_monogram: "M",
  logo_url: null,
};

const logout = vi.fn();

describe("useDashboardPage module gating", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    getMyMemberRecordMock.mockResolvedValue({ id: "member-1" } as any);
    getMySavingsMock.mockResolvedValue({
      member_id: "member-1",
      savings_balance: "0.00",
      months_contributed: 0,
    });
    getMyDeductionsMock.mockResolvedValue({
      month: "2026-11-01",
      status: null,
      contribution: "0.00",
      loan_repayment: "0.00",
      other: "0.00",
      total: "0.00",
    });
    getMemberLoanBalanceMock.mockResolvedValue({
      member_id: "member-1",
      active_loan_count: 0,
      total_outstanding_balance: "0.00",
      conflicted: false,
    });
    getNotificationsMock.mockResolvedValue({ items: [], total: 0, unread_count: 0 });
    getSettingsMock.mockResolvedValue(settings);
    listLoanApplicationsMock.mockResolvedValue([]);
    listLoansMock.mockResolvedValue([]);
    listLoanTypesMock.mockResolvedValue([]);
    listRepaymentsForLoanMock.mockResolvedValue([]);
  });

  it("loads loan data when the Loans module is enabled", async () => {
    const { result } = renderHook(() => useDashboardPage(false, user, logout));

    await waitFor(() => expect(result.current.loading).toBe(false));

    expect(listLoanApplicationsMock).toHaveBeenCalledTimes(1);
    expect(listLoansMock).toHaveBeenCalledTimes(1);
    expect(listLoanTypesMock).toHaveBeenCalledTimes(1);
    expect(getMySavingsMock).toHaveBeenCalledTimes(1);
    expect(getMyDeductionsMock).toHaveBeenCalledTimes(1);
    expect(getMemberLoanBalanceMock).toHaveBeenCalledWith("member-1");
    expect(getNotificationsMock).toHaveBeenCalledTimes(1);
    expect(result.current.loansEnabled).toBe(true);
  });

  it("skips every loan request when the Loans module is disabled", async () => {
    getSettingsMock.mockResolvedValue({ ...settings, loans_module_enabled: false });

    const { result } = renderHook(() => useDashboardPage(false, user, logout));

    await waitFor(() => expect(result.current.loading).toBe(false));

    expect(listLoanApplicationsMock).not.toHaveBeenCalled();
    expect(listLoansMock).not.toHaveBeenCalled();
    expect(listLoanTypesMock).not.toHaveBeenCalled();
    expect(getMemberLoanBalanceMock).not.toHaveBeenCalled();
    expect(listRepaymentsForLoanMock).not.toHaveBeenCalled();
    expect(result.current.loansEnabled).toBe(false);
    expect(result.current.applications.items).toEqual([]);
    expect(result.current.loans.items).toEqual([]);
    expect(result.current.apply.applyableTypes).toEqual([]);
    expect(result.current.feedback.error).toBeNull();
  });

  it("skips the deduction read when the Deductions module is disabled", async () => {
    getSettingsMock.mockResolvedValue({ ...settings, deductions_module_enabled: false });

    const { result } = renderHook(() => useDashboardPage(false, user, logout));

    await waitFor(() => expect(result.current.loading).toBe(false));

    expect(getMyDeductionsMock).not.toHaveBeenCalled();
    expect(result.current.deductionsEnabled).toBe(false);
    expect(result.current.summary.deductions).toBeNull();
  });
});

describe("useDashboardPage application submission", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    getMyMemberRecordMock.mockResolvedValue({ id: "member-1" } as any);
    getMySavingsMock.mockResolvedValue({} as any);
    getMyDeductionsMock.mockResolvedValue({} as any);
    getMemberLoanBalanceMock.mockResolvedValue({} as any);
    getNotificationsMock.mockResolvedValue({ items: [], total: 0, unread_count: 0 });
    getSettingsMock.mockResolvedValue(settings);
    listLoanApplicationsMock.mockResolvedValue([]);
    listLoansMock.mockResolvedValue([]);
    listLoanTypesMock.mockResolvedValue([
      {
        id: "type-1",
        name: "Quick Loan",
        interest_rate: "10.00",
        tenure_months: 6,
        is_active: true,
        open_for_application: true,
      } as any,
    ]);
  });

  it("advances instead of submitting when Enter is pressed before review", async () => {
    const { result } = renderHook(() => useDashboardPage(false, user, logout));
    await waitFor(() => expect(result.current.loading).toBe(false));

    act(() => {
      result.current.apply.toggle();
      result.current.apply.setField("loan_type_id", "type-1");
      result.current.apply.setField("requested_amount", 50000);
      result.current.apply.setField("payment_reference", "TRF-ENTER-1");
      result.current.apply.setReceiptFile(
        new File(["receipt"], "receipt.png", { type: "image/png" })
      );
    });

    await act(async () => {
      await result.current.apply.submit({ preventDefault: () => {} } as any);
    });

    expect(result.current.apply.step).toBe(2);

    await act(async () => {
      await result.current.apply.submit({ preventDefault: () => {} } as any);
    });
    expect(result.current.apply.step).toBe(3);

    await act(async () => {
      await result.current.apply.submit({ preventDefault: () => {} } as any);
    });
    expect(result.current.apply.step).toBe(4);
    expect(submitLoanApplicationMock).not.toHaveBeenCalled();
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
