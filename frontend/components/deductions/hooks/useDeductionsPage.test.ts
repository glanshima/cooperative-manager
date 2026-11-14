import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  ApiError,
  bulkDeductions,
  confirmDeduction,
  createDeduction,
  getDeductionSchedule,
  getDeductionWorklist,
  getSubmittableDeductionIds,
  listDeductions,
  listLoans,
  listMembers,
  voidDeduction,
} from "@/lib/api";
import type {
  DeductionWorklistEntryState,
  DeductionWorklistItem,
  DeductionWorklistOut,
  PayrollDeduction,
  PayrollDeductionSchedule,
} from "@/lib/api";
import { readStoredPageSize, storePageSize } from "@/lib/pageSize";

import { useDeductionsPage } from "./useDeductionsPage";

vi.mock("@/lib/api", () => ({
  ApiError: class ApiError extends Error {
    detail: unknown;
    transport: boolean;
    constructor(message: string, detail?: unknown, transport = false) {
      super(message);
      this.name = "ApiError";
      this.detail = detail;
      this.transport = transport;
    }
  },
  BULK_CHUNK_SIZE: 25,
  LEDGER_PAGE_SIZE: 50,
  QUEUE_PAGE_SIZE: 20,
  bulkDeductions: vi.fn(),
  confirmDeduction: vi.fn(),
  createDeduction: vi.fn(),
  getDeductionSchedule: vi.fn(),
  getDeductionWorklist: vi.fn(),
  getSubmittableDeductionIds: vi.fn(),
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
const getSubmittableMock = vi.mocked(getSubmittableDeductionIds);
const getScheduleMock = vi.mocked(getDeductionSchedule);
const getWorklistMock = vi.mocked(getDeductionWorklist);
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
    arrears_total: "0.00",
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

function makePage(records: PayrollDeduction[]) {
  return { items: records, total: records.length, skip: 0, limit: 50 };
}

function makeSchedule(records: PayrollDeduction[]): PayrollDeductionSchedule {
  return {
    month: "2026-11-01",
    records,
    totals: {
      contribution_total: "2000.00",
      loan_total: "500.00",
      arrears_total: "0.00",
      other_total: "100.00",
      grand_total: "2600.00",
    },
  };
} // Ensure this matches the type definition

function makeWorklistItem(overrides: Partial<DeductionWorklistItem> = {}): DeductionWorklistItem {
  return {
    member_id: "member-1",
    member_name: "Test Member",
    member_psn: "PSN-1",
    member_status: "financial",
    membership_exit_date: null,
    due_reasons: ["Monthly contribution due"],
    lines: [
      { category: "monthly_contribution", amount: "5000.00", arrears: "0.00", months_behind: 0 },
      {
        category: "loan_repayment",
        amount: "1000.00",
        loan_id: "loan-1",
        loan_type_name: "Regular loan",
        arrears: "2000.00",
        months_behind: 2,
      },
      {
        category: "loan_arrears",
        amount: "2000.00",
        loan_id: "loan-1",
        loan_type_name: "Regular loan",
        arrears: "2000.00",
        months_behind: 2,
      },
    ],
    warnings: [],
    expected_total: "8000.00",
    deduction_id: null,
    deduction_status: null,
    conflicted: false,
    ...overrides,
  };
}

const logout = vi.fn();

function makeWorklistOut(
  items: DeductionWorklistItem[],
  overrides: Partial<DeductionWorklistOut> = {}
): DeductionWorklistOut {
  return {
    month: "2026-11-01",
    items,
    total: items.length,
    skip: 0,
    limit: 20,
    entry_state: "pending",
    due_count: items.length,
    pending_count: items.length,
    entered_count: 0,
    expected_total: "0.00",
    ...overrides,
  };
}

describe("useDeductionsPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // A page size chosen in one test must not follow the next one around.
    window.localStorage.clear();
    const records = [makeDeduction()];
    listDeductionsMock.mockResolvedValue(makePage(records));
    getScheduleMock.mockResolvedValue(makeSchedule(records));
    listMembersMock.mockResolvedValue({ items: [], total: 0, skip: 0, limit: 1000 });
    listLoansMock.mockResolvedValue([]);
    getWorklistMock.mockResolvedValue(makeWorklistOut([]));
  });

  it("loads the month's deductions and schedule totals", async () => {
    const { result } = renderHook(() => useDeductionsPage(logout));

    await waitFor(() => expect(result.current.table.loading).toBe(false));

    expect(listDeductionsMock).toHaveBeenCalledWith({
      month: expect.any(String),
      status: undefined,
      skip: 0,
      limit: 50,
    });
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

  it("pages the ledger and drops the stale selection", async () => {
    const page1 = [makeDeduction({ id: "page1-1" })];
    listDeductionsMock.mockResolvedValue({ items: page1, total: 120, skip: 0, limit: 50 });
    const { result } = renderHook(() => useDeductionsPage(logout));
    await waitFor(() => expect(result.current.table.loading).toBe(false));

    act(() => result.current.table.toggleSelected("page1-1"));
    expect(result.current.table.selected).toEqual(["page1-1"]);

    listDeductionsMock.mockResolvedValue({
      items: [makeDeduction({ id: "page2-1" })],
      total: 120,
      skip: 50,
      limit: 50,
    });
    await act(async () => {
      result.current.table.pagination.goToPage(50);
    });

    await waitFor(() =>
      expect(listDeductionsMock).toHaveBeenLastCalledWith(
        expect.objectContaining({ skip: 50, limit: 50 })
      )
    );
    expect(result.current.table.pagination.total).toBe(120);
    expect(result.current.table.selected).toEqual([]);
  });

  it("sizes both lists from one choice once the officer makes it", async () => {
    const { result } = renderHook(() => useDeductionsPage(logout));
    await waitFor(() => expect(result.current.table.loading).toBe(false));

    // Until then each list keeps the size that suits it: a ledger row is a
    // table line, a queue entry is a card with its expected amounts.
    expect(result.current.table.pagination.limit).toBe(50);
    expect(result.current.worklist.pagination.limit).toBe(20);

    await act(async () => {
      result.current.pageSize.change(100);
    });

    expect(result.current.pageSize.chosen).toBe(100);
    await waitFor(() =>
      expect(listDeductionsMock).toHaveBeenLastCalledWith(
        expect.objectContaining({ limit: 100, skip: 0 })
      )
    );
    await waitFor(() =>
      expect(getWorklistMock).toHaveBeenLastCalledWith(
        expect.any(String),
        expect.objectContaining({ limit: 100, skip: 0 })
      )
    );
    expect(readStoredPageSize()).toBe(100);
  });

  it("applies the size this officer chose last time before they ask again", async () => {
    storePageSize(20);
    listDeductionsMock.mockResolvedValue({ items: [], total: 0, skip: 0, limit: 20 });

    const { result } = renderHook(() => useDeductionsPage(logout));

    await waitFor(() =>
      expect(listDeductionsMock).toHaveBeenLastCalledWith(expect.objectContaining({ limit: 20 }))
    );
    expect(result.current.pageSize.chosen).toBe(20);
    expect(result.current.worklist.pagination.limit).toBe(20);
  });

  it("sends bulk actions in chunks of 25", async () => {
    const ids = Array.from({ length: 30 }, (_, index) => `deduction-${index}`);
    bulkDeductionsMock.mockImplementation(async (_action, chunk) => ({
      results: chunk.map((id) => ({ id, ok: true, status: "submitted" })),
    }));
    const { result } = renderHook(() => useDeductionsPage(logout));
    await waitFor(() => expect(result.current.table.loading).toBe(false));

    await act(async () => {
      result.current.actions.request("submit", ids);
    });

    await waitFor(() => expect(bulkDeductionsMock).toHaveBeenCalledTimes(2));
    expect(bulkDeductionsMock.mock.calls[0][1]).toHaveLength(25);
    expect(bulkDeductionsMock.mock.calls[1][1]).toHaveLength(5);
    expect(result.current.feedback.message).toBe("30 of 30 deductions updated.");
  });

  it("collapses repeated bulk failures instead of listing each one", async () => {
    bulkDeductionsMock.mockResolvedValue({
      results: [
        { id: "deduction-1", ok: false, detail: "Only draft deductions can be submitted" },
        { id: "deduction-2", ok: false, detail: "Only draft deductions can be submitted" },
      ],
    });
    const { result } = renderHook(() => useDeductionsPage(logout));
    await waitFor(() => expect(result.current.table.loading).toBe(false));

    await act(async () => {
      result.current.actions.request("submit", ["deduction-1", "deduction-2"]);
    });

    expect(result.current.feedback.error).toBe(
      "Only draft deductions can be submitted (×2)"
    );
  });

  it("previews the submit-all scope before sending anything", async () => {
    getSubmittableMock.mockResolvedValue({
      month: "2026-11-01",
      ids: ["deduction-1", "deduction-2"],
      empty_draft_ids: ["deduction-3"],
    });
    const { result } = renderHook(() => useDeductionsPage(logout));
    await waitFor(() => expect(result.current.table.loading).toBe(false));

    await act(async () => {
      await result.current.actions.submitAll.request();
    });

    expect(bulkDeductionsMock).not.toHaveBeenCalled();
    expect(result.current.actions.submitAll.preview).toMatchObject({
      ids: ["deduction-1", "deduction-2"],
      emptyCount: 1,
    });
  });

  it("submits the previewed scope and reports what stayed back", async () => {
    getSubmittableMock.mockResolvedValue({
      month: "2026-11-01",
      ids: ["deduction-1", "deduction-2"],
      empty_draft_ids: ["deduction-3"],
    });
    bulkDeductionsMock.mockResolvedValue({
      results: [
        { id: "deduction-1", ok: true, status: "submitted" },
        {
          id: "deduction-2",
          ok: false,
          detail: "Conflicted officer may not submit an overridden deduction",
        },
      ],
    });
    const { result } = renderHook(() => useDeductionsPage(logout));
    await waitFor(() => expect(result.current.table.loading).toBe(false));

    await act(async () => {
      await result.current.actions.submitAll.request();
    });
    await act(async () => {
      await result.current.actions.submitAll.confirm();
    });

    expect(result.current.feedback.message).toBe(
      "1 of 2 drafts submitted · 1 left as drafts (no lines) · 1 refused"
    );
    expect(result.current.feedback.error).toContain("Conflicted officer");
    expect(result.current.actions.submitAll.preview).toBeNull();
  });

  it("says so when no draft in the month can be submitted", async () => {
    getSubmittableMock.mockResolvedValue({
      month: "2026-11-01",
      ids: [],
      empty_draft_ids: ["deduction-3"],
    });
    const { result } = renderHook(() => useDeductionsPage(logout));
    await waitFor(() => expect(result.current.table.loading).toBe(false));

    await act(async () => {
      await result.current.actions.submitAll.request();
    });

    expect(bulkDeductionsMock).not.toHaveBeenCalled();
    expect(result.current.feedback.message).toContain("have no lines yet");
  });
});

describe("useDeductionsPage enter queue", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    window.localStorage.clear();
    const records = [makeDeduction()];
    listDeductionsMock.mockResolvedValue(makePage(records));
    getScheduleMock.mockResolvedValue(makeSchedule(records));
    listMembersMock.mockResolvedValue({ items: [], total: 0, skip: 0, limit: 1000 });
    listLoansMock.mockResolvedValue([]);
    getWorklistMock.mockResolvedValue(
      makeWorklistOut([makeWorklistItem()], {
        due_count: 1,
        pending_count: 1,
        expected_total: "8000.00",
      })
    );
  });

  it("loads the pending queue on mount, one page at a time", async () => {
    const { result } = renderHook(() => useDeductionsPage(logout));

    await waitFor(() => expect(result.current.worklist.loading).toBe(false));

    expect(getWorklistMock).toHaveBeenCalledWith(expect.any(String), {
      entry_state: "pending",
      skip: 0,
      limit: 20,
    });
    expect(result.current.tab).toBe("enter");
    expect(result.current.worklist.data?.items).toHaveLength(1);
    expect(result.current.worklist.data?.due_count).toBe(1);
    expect(result.current.worklist.error).toBeNull();
  });

  it("opens the form prefilled with the server's expected amounts", async () => {
    const { result } = renderHook(() => useDeductionsPage(logout));
    await waitFor(() => expect(result.current.worklist.loading).toBe(false));

    act(() => {
      result.current.worklist.openItem(makeWorklistItem());
    });

    expect(result.current.form.open).toBe(true);
    expect(result.current.form.editing).toBeNull();
    expect(result.current.form.prefill).toEqual({
      memberId: "member-1",
      memberName: "Test Member",
      memberStatus: "financial",
      month: result.current.filters.month,
      contribution: "5000.00",
      loanLines: [
        {
          key: "loan-1:loan_repayment",
          loanId: "loan-1",
          category: "loan_repayment",
          loanName: "Regular loan",
          label: "Regular loan",
          amount: "1000.00",
        },
        {
          key: "loan-1:loan_arrears",
          loanId: "loan-1",
          category: "loan_arrears",
          loanName: "Regular loan",
          label: "Arrears on Regular loan — 2 months behind",
          amount: "2000.00",
        },
      ],
      conflicted: false,
    });
  });

  it("carries the conflict flag through to the prefill", async () => {
    const { result } = renderHook(() => useDeductionsPage(logout));
    await waitFor(() => expect(result.current.worklist.loading).toBe(false));

    act(() => {
      result.current.worklist.openItem(makeWorklistItem({ conflicted: true }));
    });

    expect(result.current.form.prefill?.conflicted).toBe(true);
  });

  it("offers a one-click undo after creating a draft from the queue", async () => {
    createDeductionMock.mockResolvedValue(makeDeduction({ id: "deduction-new" }));
    voidDeductionMock.mockResolvedValue(makeDeduction({ id: "deduction-new", status: "void" }));
    const { result } = renderHook(() => useDeductionsPage(logout));
    await waitFor(() => expect(result.current.worklist.loading).toBe(false));

    act(() => {
      result.current.worklist.openItem(makeWorklistItem());
    });
    await act(async () => {
      await result.current.form.save({
        member_id: "member-1",
        deduction_month: "2026-11",
        lines: [
          { category: "monthly_contribution", amount: 5000 },
          { category: "loan_repayment", loan_id: "loan-1", amount: 1000 },
        ],
      });
    });

    expect(result.current.worklist.lastEntered).toEqual({
      id: "deduction-new",
      memberName: "Test Member",
    });
    expect(result.current.form.open).toBe(false);
    expect(result.current.form.prefill).toBeNull();

    await act(async () => {
      await result.current.worklist.undo();
    });

    expect(voidDeductionMock).toHaveBeenCalledWith("deduction-new", "Entered in error");
    await waitFor(() => expect(result.current.worklist.lastEntered).toBeNull());
    expect(result.current.feedback.message).toBe("Entry for Test Member undone.");
  });

  it("sends a replacement arrears draft after the previous entry was voided", async () => {
    createDeductionMock
      .mockResolvedValueOnce(makeDeduction({ id: "deduction-first" }))
      .mockResolvedValueOnce(makeDeduction({ id: "deduction-replacement" }));
    voidDeductionMock.mockResolvedValue(
      makeDeduction({ id: "deduction-first", status: "void" })
    );
    const { result } = renderHook(() => useDeductionsPage(logout));
    await waitFor(() => expect(result.current.worklist.loading).toBe(false));

    const lines = [
      { category: "loan_repayment" as const, loan_id: "loan-1", amount: 1000 },
      { category: "loan_arrears" as const, loan_id: "loan-1", amount: 2000 },
    ];
    const save = () =>
      result.current.form.save({
        member_id: "member-1",
        deduction_month: "2026-11",
        lines,
      });

    act(() => result.current.worklist.openItem(makeWorklistItem()));
    await act(async () => {
      await save();
    });
    await act(async () => {
      await result.current.worklist.undo();
    });

    act(() => result.current.worklist.openItem(makeWorklistItem()));
    await act(async () => {
      await save();
    });

    expect(createDeductionMock).toHaveBeenCalledTimes(2);
    expect(createDeductionMock).toHaveBeenLastCalledWith(
      expect.objectContaining({
        lines: expect.arrayContaining([
          { category: "loan_arrears", loan_id: "loan-1", amount: 2000 },
        ]),
      })
    );
    expect(result.current.worklist.lastEntered?.id).toBe("deduction-replacement");
  });

  it("reports an unreachable server without claiming the draft was lost", async () => {
    createDeductionMock.mockRejectedValue(
      new ApiError("Could not reach the server.", undefined, true)
    );
    const { result } = renderHook(() => useDeductionsPage(logout));
    await waitFor(() => expect(result.current.worklist.loading).toBe(false));

    act(() => result.current.worklist.openItem(makeWorklistItem()));
    // The ledger has no row for this member/month, so the create truly failed.
    listDeductionsMock.mockResolvedValue({ items: [], total: 0, skip: 0, limit: 1 });

    await act(async () => {
      await result.current.form.save({
        member_id: "member-1",
        deduction_month: "2026-11",
        lines: [{ category: "loan_arrears", loan_id: "loan-1", amount: 2000 }],
      });
    });

    expect(result.current.form.open).toBe(true);
    expect(result.current.feedback.error).toContain("Could not reach the server");
  });

  it("treats a draft found in the ledger as saved when the reply never arrives", async () => {
    createDeductionMock.mockRejectedValue(
      new ApiError("Could not reach the server.", undefined, true)
    );
    const { result } = renderHook(() => useDeductionsPage(logout));
    await waitFor(() => expect(result.current.worklist.loading).toBe(false));

    act(() => result.current.worklist.openItem(makeWorklistItem()));
    // The insert committed; only the response was lost on the way back.
    listDeductionsMock.mockResolvedValue({
      items: [makeDeduction({ id: "deduction-saved" })],
      total: 1,
      skip: 0,
      limit: 1,
    });

    await act(async () => {
      await result.current.form.save({
        member_id: "member-1",
        deduction_month: "2026-11",
        lines: [{ category: "loan_arrears", loan_id: "loan-1", amount: 2000 }],
      });
    });

    expect(result.current.form.open).toBe(false);
    expect(result.current.feedback.message).toContain("Draft saved");
    expect(result.current.feedback.error).toBeNull();
    expect(result.current.worklist.lastEntered).toEqual({
      id: "deduction-saved",
      memberName: "Test Member",
    });
  });

  it("does not offer undo for a draft created outside the queue", async () => {
    createDeductionMock.mockResolvedValue(makeDeduction({ id: "deduction-new" }));
    const { result } = renderHook(() => useDeductionsPage(logout));
    await waitFor(() => expect(result.current.table.loading).toBe(false));

    act(() => {
      result.current.form.openCreate();
    });
    await act(async () => {
      await result.current.form.save({
        member_id: "member-1",
        deduction_month: "2026-11",
        lines: [{ category: "monthly_contribution", amount: 5000 }],
      });
    });

    expect(result.current.worklist.lastEntered).toBeNull();
  });

  it("switches to the entered segment and starts it at page one", async () => {
    getWorklistMock.mockResolvedValue(
      makeWorklistOut([makeWorklistItem({ deduction_id: "deduction-1", deduction_status: "draft" })], {
        entry_state: "entered",
        total: 1,
        due_count: 42,
        pending_count: 41,
        entered_count: 1,
      })
    );
    const { result } = renderHook(() => useDeductionsPage(logout));
    await waitFor(() => expect(result.current.worklist.loading).toBe(false));

    await act(async () => {
      result.current.worklist.setEntryState("entered");
    });

    await waitFor(() =>
      expect(getWorklistMock).toHaveBeenLastCalledWith(result.current.filters.month, {
        entry_state: "entered",
        skip: 0,
        limit: 20,
      })
    );
    expect(result.current.worklist.entryState).toBe("entered");
    // The segment lists one member; the month still has 42 waiting.
    expect(result.current.worklist.data?.items).toHaveLength(1);
    expect(result.current.worklist.data?.pending_count).toBe(41);
  });

  it("pages the queue without dropping the officer out of the segment", async () => {
    getWorklistMock.mockResolvedValue(
      makeWorklistOut([makeWorklistItem()], { total: 25, skip: 20 })
    );
    const { result } = renderHook(() => useDeductionsPage(logout));
    await waitFor(() => expect(result.current.worklist.loading).toBe(false));

    await act(async () => {
      result.current.worklist.pagination.goToPage(20);
    });

    await waitFor(() =>
      expect(getWorklistMock).toHaveBeenLastCalledWith(expect.any(String), {
        entry_state: "pending",
        skip: 20,
        limit: 20,
      })
    );
    expect(result.current.worklist.pagination.total).toBe(25);
    expect(result.current.worklist.pagination.skip).toBe(20);
  });

  it("moves the officer to a page that still has rows after the queue shrinks", async () => {
    getWorklistMock
      .mockResolvedValueOnce(makeWorklistOut([makeWorklistItem()], { total: 61 }))
      .mockResolvedValueOnce(
        makeWorklistOut([], { total: 40, skip: 40, due_count: 40, pending_count: 40 })
      )
      .mockResolvedValue(
        makeWorklistOut([makeWorklistItem({ member_id: "member-2" })], {
          total: 40,
          skip: 20,
          due_count: 40,
          pending_count: 40,
        })
      );
    const { result } = renderHook(() => useDeductionsPage(logout));
    await waitFor(() => expect(result.current.worklist.loading).toBe(false));

    await act(async () => {
      result.current.worklist.pagination.goToPage(40);
    });

    // The officer was on page 3 of 4; entering members cut the month to two
    // pages, so the queue asks for the last page that still has rows.
    await waitFor(() =>
      expect(getWorklistMock).toHaveBeenLastCalledWith(expect.any(String), {
        entry_state: "pending",
        skip: 20,
        limit: 20,
      })
    );
    expect(result.current.worklist.pagination.skip).toBe(20);
    expect(result.current.worklist.data?.items[0].member_id).toBe("member-2");
  });

  it("surfaces a worklist load failure without breaking the ledger", async () => {
    getWorklistMock.mockRejectedValue(new Error("Deductions module is disabled"));
    const { result } = renderHook(() => useDeductionsPage(logout));

    await waitFor(() => expect(result.current.worklist.loading).toBe(false));

    expect(result.current.worklist.error).toBe("Deductions module is disabled");
    expect(result.current.worklist.data).toBeNull();
    expect(result.current.table.items).toHaveLength(1);
  });

  it("confirms only the submitted rows of a mixed selection", async () => {
    const records = [
      makeDeduction({ id: "submitted-1", status: "submitted" }),
      makeDeduction({ id: "submitted-2", status: "submitted" }),
      makeDeduction({ id: "draft-1", status: "draft" }),
    ];
    listDeductionsMock.mockResolvedValue(makePage(records));
    getScheduleMock.mockResolvedValue(makeSchedule(records));
    bulkDeductionsMock.mockResolvedValue({
      results: [
        { id: "submitted-1", ok: true, status: "confirmed" },
        { id: "submitted-2", ok: true, status: "confirmed" },
      ],
    });

    const { result } = renderHook(() => useDeductionsPage(logout));
    await waitFor(() => expect(result.current.table.loading).toBe(false));

    act(() => result.current.table.toggleAll(["submitted-1", "submitted-2", "draft-1"]));
    expect(result.current.table.eligible.confirm).toBe(2);
    expect(result.current.table.eligible.submit).toBe(1);

    await act(async () => {
      await result.current.actions.request("confirm", result.current.table.selected);
    });

    expect(bulkDeductionsMock).toHaveBeenCalledWith(
      "confirm",
      ["submitted-1", "submitted-2"],
      undefined
    );
    expect(result.current.feedback.message).toBe(
      "2 of 2 deductions updated. 1 skipped — only submitted deductions can be confirmed."
    );
    expect(result.current.feedback.error).toBeNull();
  });

  it("refuses a bulk action when no selected row is in a state it applies to", async () => {
    const records = [
      makeDeduction({ id: "draft-1", status: "draft" }),
      makeDeduction({ id: "draft-2", status: "draft" }),
    ];
    listDeductionsMock.mockResolvedValue(makePage(records));
    getScheduleMock.mockResolvedValue(makeSchedule(records));

    const { result } = renderHook(() => useDeductionsPage(logout));
    await waitFor(() => expect(result.current.table.loading).toBe(false));

    act(() => result.current.table.toggleAll(["draft-1", "draft-2"]));
    expect(result.current.table.eligible.confirm).toBe(0);

    await act(async () => {
      await result.current.actions.request("confirm", result.current.table.selected);
    });

    expect(confirmDeductionMock).not.toHaveBeenCalled();
    expect(bulkDeductionsMock).not.toHaveBeenCalled();
    expect(result.current.feedback.error).toBe(
      "Nothing to confirm in this selection — only submitted deductions can be confirmed."
    );
  });

  it("lets the officer dismiss feedback without waiting for it to clear", async () => {
    confirmDeductionMock.mockResolvedValue(makeDeduction({ status: "confirmed" }));
    const { result } = renderHook(() => useDeductionsPage(logout));
    await waitFor(() => expect(result.current.table.loading).toBe(false));

    await act(async () => {
      await result.current.actions.request("confirm", ["deduction-1"]);
    });
    expect(result.current.feedback.message).toBe("Confirm deduction completed.");

    act(() => result.current.feedback.dismissMessage());
    expect(result.current.feedback.message).toBeNull();

    confirmDeductionMock.mockRejectedValueOnce(new Error("Only submitted deductions can be confirmed"));
    await act(async () => {
      await result.current.actions.request("confirm", ["deduction-1"]);
    });
    expect(result.current.feedback.error).toBe("Only submitted deductions can be confirmed");
    act(() => result.current.feedback.dismissError());
    expect(result.current.feedback.error).toBeNull();
  });

  it("clears feedback on its own after the timeout", async () => {
    confirmDeductionMock.mockResolvedValue(makeDeduction({ status: "confirmed" }));
    const { result } = renderHook(() => useDeductionsPage(logout));
    await waitFor(() => expect(result.current.table.loading).toBe(false));

    vi.useFakeTimers();
    try {
      await act(async () => {
        await result.current.actions.request("confirm", ["deduction-1"]);
      });
      expect(result.current.feedback.message).toBe("Confirm deduction completed.");

      act(() => {
        vi.advanceTimersByTime(10_000);
      });
      expect(result.current.feedback.message).toBeNull();
    } finally {
      vi.useRealTimers();
    }
  });
});
