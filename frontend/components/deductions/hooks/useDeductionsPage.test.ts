import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  bulkDeductions,
  confirmDeduction,
  createDeduction,
  getDeductionSchedule,
  listDeductions,
  listLoans,
  listMembers,
  voidDeduction,
} from "@/lib/api";
import type { PayrollDeduction, PayrollDeductionSchedule } from "@/lib/api";

import { useDeductionsPage } from "./useDeductionsPage";

vi.mock("@/lib/api", () => ({
  bulkDeductions: vi.fn(),
  confirmDeduction: vi.fn(),
  createDeduction: vi.fn(),
  getDeductionSchedule: vi.fn(),
  listDeductions: vi.fn(),
  listLoans: vi.fn(),
  listMembers: vi.fn(),
  markDeductionNotDeducted: vi.fn(),
  returnDeductionToDraft: vi.fn(),
  submitDeduction: vi.fn(),
  updateDeduction: vi.fn(),
  voidDeduction: vi.fn(),
}));

const listDeductionsMock = vi.mocked(listDeductions);
const getScheduleMock = vi.mocked(getDeductionSchedule);
const listMembersMock = vi.mocked(listMembers);
const listLoansMock = vi.mocked(listLoans);
const confirmDeductionMock = vi.mocked(confirmDeduction);
const voidDeductionMock = vi.mocked(voidDeduction);
const bulkDeductionsMock = vi.mocked(bulkDeductions);
const createDeductionMock = vi.mocked(createDeduction);

function makeDeduction(overrides: Partial<PayrollDeduction> = {}): PayrollDeduction {
  return {
    id: "deduction-1",
    member_id: "member-1",
    member_name: "Test Member",
    member_psn: "PSN-1",
    deduction_month: "2026-11-01",
    payroll_reference: "PAY-2026-11",
    note: null,
    status: "draft",
    contribution_total: "2000.00",
    loan_total: "500.00",
    other_total: "100.00",
    grand_total: "2600.00",
    submitted_at: null,
    confirmed_at: null,
    not_deducted_at: null,
    not_deducted_reason: null,
    returned_at: null,
    return_reason: null,
    voided_at: null,
    void_reason: null,
    created_at: "2026-11-01T00:00:00Z",
    updated_at: "2026-11-01T00:00:00Z",
    lines: [],
    ...overrides,
  };
}

function makeSchedule(records: PayrollDeduction[]): PayrollDeductionSchedule {
  return {
    month: "2026-11-01",
    records,
    totals: {
      contribution_total: "2000.00",
      loan_total: "500.00",
      other_total: "100.00",
      grand_total: "2600.00",
    },
  };
}

const logout = vi.fn();

describe("useDeductionsPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    const records = [makeDeduction()];
    listDeductionsMock.mockResolvedValue(records);
    getScheduleMock.mockResolvedValue(makeSchedule(records));
    listMembersMock.mockResolvedValue({ items: [], total: 0, skip: 0, limit: 1000 });
    listLoansMock.mockResolvedValue([]);
  });

  it("loads the month's deductions and schedule totals", async () => {
    const { result } = renderHook(() => useDeductionsPage(logout));

    await waitFor(() => expect(result.current.table.loading).toBe(false));

    expect(listDeductionsMock).toHaveBeenCalledWith({ month: expect.any(String), status: undefined });
    expect(getScheduleMock).toHaveBeenCalledWith(expect.any(String));
    expect(result.current.table.items).toHaveLength(1);
    expect(result.current.totals?.grand_total).toBe("2600.00");
    expect(result.current.feedback.error).toBeNull();
  });

  it("confirms a single deduction and refreshes", async () => {
    confirmDeductionMock.mockResolvedValue(makeDeduction({ status: "confirmed" }));
    const { result } = renderHook(() => useDeductionsPage(logout));
    await waitFor(() => expect(result.current.table.loading).toBe(false));

    await act(async () => {
      result.current.actions.request("confirm", ["deduction-1"]);
    });

    await waitFor(() => expect(confirmDeductionMock).toHaveBeenCalledWith("deduction-1"));
    await waitFor(() => expect(result.current.feedback.busy).toBe(false));
    expect(result.current.feedback.message).toBe("Confirm deduction completed.");
    expect(listDeductionsMock).toHaveBeenCalledTimes(2);
  });

  it("collects a reason before voiding", async () => {
    voidDeductionMock.mockResolvedValue(makeDeduction({ status: "void" }));
    const { result } = renderHook(() => useDeductionsPage(logout));
    await waitFor(() => expect(result.current.table.loading).toBe(false));

    act(() => {
      result.current.actions.request("void", ["deduction-1"]);
    });
    expect(result.current.actions.pending?.action).toBe("void");

    act(() => {
      result.current.actions.setReason("Wrong month");
    });
    await act(async () => {
      result.current.actions.confirmPending();
    });

    await waitFor(() =>
      expect(voidDeductionMock).toHaveBeenCalledWith("deduction-1", "Wrong month")
    );
    await waitFor(() => expect(result.current.actions.pending).toBeNull());
  });

  it("reports per-record bulk results", async () => {
    bulkDeductionsMock.mockResolvedValue({
      results: [
        { id: "deduction-1", ok: true, status: "not_deducted" },
        { id: "deduction-2", ok: false, detail: "Only submitted deductions can be marked not deducted" },
      ],
    });
    const { result } = renderHook(() => useDeductionsPage(logout));
    await waitFor(() => expect(result.current.table.loading).toBe(false));

    act(() => {
      result.current.actions.request("not_deducted", ["deduction-1", "deduction-2"]);
      result.current.actions.setReason("Payroll skipped");
    });
    await act(async () => {
      result.current.actions.confirmPending();
    });

    await waitFor(() =>
      expect(bulkDeductionsMock).toHaveBeenCalledWith(
        "not-deducted",
        ["deduction-1", "deduction-2"],
        "Payroll skipped"
      )
    );
    await waitFor(() =>
      expect(result.current.feedback.message).toBe("1 of 2 deductions updated.")
    );
    expect(result.current.feedback.error).toContain("Only submitted deductions");
  });

  it("creates a draft through the form slice", async () => {
    createDeductionMock.mockResolvedValue(makeDeduction());
    const { result } = renderHook(() => useDeductionsPage(logout));
    await waitFor(() => expect(result.current.table.loading).toBe(false));

    await act(async () => {
      await result.current.form.save({
        member_id: "member-1",
        deduction_month: "2026-11",
        lines: [{ category: "monthly_contribution", amount: 2000 }],
      });
    });

    expect(createDeductionMock).toHaveBeenCalledWith({
      member_id: "member-1",
      deduction_month: "2026-11",
      lines: [{ category: "monthly_contribution", amount: 2000 }],
    });
    expect(result.current.feedback.message).toBe("Draft created.");
  });
});
