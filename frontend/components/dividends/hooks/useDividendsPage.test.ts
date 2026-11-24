import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  createDividendRun,
  declareDividendRun,
  deleteDividendRun,
  getDividendManifest,
  getDividendRun,
  getDividendSummary,
  listDividendAllocations,
  listDividendRuns,
  recomputeDividendRun,
  recordDividendPayout,
} from "@/lib/api";
import type {
  DividendAllocation,
  DividendAllocationPage,
  DividendRun,
  DividendRunDetail,
  DividendSummary,
} from "@/lib/api";

import { todayIso } from "../labels";
import { useDividendsPage } from "./useDividendsPage";

vi.mock("@/lib/api", () => ({
  createDividendRun: vi.fn(),
  declareDividendRun: vi.fn(),
  deleteDividendRun: vi.fn(),
  getDividendManifest: vi.fn(),
  getDividendRun: vi.fn(),
  getDividendSummary: vi.fn(),
  listDividendAllocations: vi.fn(),
  listDividendRuns: vi.fn(),
  recomputeDividendRun: vi.fn(),
  recordDividendPayout: vi.fn(),
}));

const summaryMock = vi.mocked(getDividendSummary);
const runsMock = vi.mocked(listDividendRuns);
const allocationsMock = vi.mocked(listDividendAllocations);
const detailMock = vi.mocked(getDividendRun);
const createMock = vi.mocked(createDividendRun);
const declareMock = vi.mocked(declareDividendRun);
const payoutMock = vi.mocked(recordDividendPayout);
const deleteMock = vi.mocked(deleteDividendRun);
const recomputeMock = vi.mocked(recomputeDividendRun);
const manifestMock = vi.mocked(getDividendManifest);

const PERMISSIONS = ["dividend.view", "dividend.declare", "dividend.pay"];

function makeSummary(overrides: Partial<DividendSummary> = {}): DividendSummary {
  return {
    fiscal_year_start_month: 1,
    basis: "net_savings_closing",
    pool_mode: "net_income_share",
    reserve_pct: "4.70",
    honorarium_pct: "3.00",
    payout_pct: "92.30",
    declared_rate_pct: null,
    fixed_pool_amount: null,
    hybrid_savings_pct: "50.00",
    min_membership_months: 0,
    include_exited: false,
    rounding: "two_dp",
    withholding_pct: "0.00",
    payment_method: "bank",
    cashbook_module_enabled: true,
    cashbook_open: true,
    last_declared_year: 2024,
    suggested_fiscal_year: 2025,
    ...overrides,
  };
}

function makeRun(overrides: Partial<DividendRun> = {}): DividendRun {
  return {
    id: "run-1",
    fiscal_year: 2025,
    period_start: "2025-01-01",
    period_end: "2025-12-31",
    status: "declared",
    basis: "net_savings_closing",
    pool_mode: "net_income_share",
    surplus: "3000",
    reserve_pct: "4.70",
    reserve_amount: "141",
    honorarium_pct: "3.00",
    honorarium_amount: "90",
    payout_pct: "92.30",
    pool_amount: "2769",
    declared_rate_pct: null,
    fixed_pool_amount: null,
    hybrid_savings_pct: "50",
    withholding_pct: "0",
    rounding: "two_dp",
    min_membership_months: 0,
    include_exited: false,
    closed_income_total: "3000",
    closed_expense_total: "0",
    total_basis_amount: "10000",
    total_gross: "2769",
    total_withholding: "0",
    total_net: "2769",
    rounding_residual: "0",
    eligible_member_count: 2,
    note: null,
    declared_on: "2026-01-05",
    declared_by_user_id: null,
    created_at: null,
    ...overrides,
  };
}

function makeAllocation(overrides: Partial<DividendAllocation> = {}): DividendAllocation {
  return {
    id: "alloc-1",
    member_id: "member-1",
    psn: "PSN-0001",
    name: "Adaeze Okafor",
    bank_name: "Zenith",
    account_number: "0123456789",
    basis_amount: "6000",
    share_ratio: "0.6",
    gross_amount: "1661.40",
    withholding_amount: "0",
    net_amount: "1661.40",
    rounding_adjustment: "0",
    payout_id: null,
    ...overrides,
  };
}

function makePage(items: DividendAllocation[]): DividendAllocationPage {
  return { items, total: items.length, skip: 0, limit: 25 };
}

function makeDetail(run: DividendRun): DividendRunDetail {
  return { run, payouts: [], paid_allocations: 0, pending_allocations: 2 };
}

const rowOne = makeAllocation();
const rowTwo = makeAllocation({
  id: "alloc-2",
  member_id: "member-2",
  psn: "PSN-0002",
  name: "Bello Musa",
  basis_amount: "4000",
  share_ratio: "0.4",
  gross_amount: "1107.60",
  net_amount: "1107.60",
});

beforeEach(() => {
  vi.clearAllMocks();
  summaryMock.mockResolvedValue(makeSummary());
  runsMock.mockResolvedValue([makeRun()]);
  detailMock.mockResolvedValue(makeDetail(makeRun()));
  allocationsMock.mockResolvedValue(makePage([rowOne, rowTwo]));
  payoutMock.mockResolvedValue({
    id: "payout-1",
    run_id: "run-1",
    paid_on: todayIso(),
    method: "bank",
    reference: "TRF-1",
    amount: "2769",
    note: null,
    created_by_user_id: null,
    created_at: null,
  });
});

describe("useDividendsPage", () => {
  it("loads the policy summary and the runs list, with no run selected", async () => {
    const { result } = renderHook(() => useDividendsPage(PERMISSIONS));

    await waitFor(() => expect(result.current.loading).toBe(false));

    expect(result.current.summary?.suggested_fiscal_year).toBe(2025);
    expect(result.current.runs).toHaveLength(1);
    expect(result.current.selectedId).toBeNull();
  });

  it("opens a run, loads its allocations and tracks a selection's amount", async () => {
    const { result } = renderHook(() => useDividendsPage(PERMISSIONS));
    await waitFor(() => expect(result.current.loading).toBe(false));

    await act(async () => {
      await result.current.openRun("run-1");
    });

    expect(detailMock).toHaveBeenCalledWith("run-1");
    expect(result.current.detail?.run.fiscal_year).toBe(2025);
    expect(result.current.allocations?.items).toHaveLength(2);

    act(() => result.current.toggleSelected(rowOne));

    expect(result.current.selectedCount).toBe(1);
    expect(result.current.selectedAmount).toBeCloseTo(1661.4);
    expect(result.current.isSelected("alloc-1")).toBe(true);

    act(() => result.current.toggleSelected(rowOne));
    expect(result.current.selectedCount).toBe(0);
  });

  it("prepares a draft for the suggested year and opens it", async () => {
    createMock.mockResolvedValue(makeRun({ status: "draft" }));
    runsMock.mockResolvedValue([makeRun({ status: "draft" })]);
    detailMock.mockResolvedValue(makeDetail(makeRun({ status: "draft" })));

    const { result } = renderHook(() => useDividendsPage(PERMISSIONS));
    await waitFor(() => expect(result.current.loading).toBe(false));

    act(() => result.current.openNewRun());
    expect(result.current.newRun.open).toBe(true);
    expect(result.current.newRun.fiscalYear).toBe("2025");

    act(() => result.current.newRun.set({ note: "  Year end  " }));
    await act(async () => {
      await result.current.submitNewRun();
    });

    expect(createMock).toHaveBeenCalledWith({ fiscal_year: 2025, note: "Year end" });
    expect(result.current.newRun.open).toBe(false);
    expect(result.current.selectedId).toBe("run-1");
    expect(result.current.feedback.success).toMatch(/Draft dividend run for 2025/);
  });

  it("declares a draft with a declaration date", async () => {
    detailMock.mockResolvedValue(makeDetail(makeRun({ status: "draft" })));
    declareMock.mockResolvedValue(makeRun({ status: "declared" }));

    const { result } = renderHook(() => useDividendsPage(PERMISSIONS));
    await waitFor(() => expect(result.current.loading).toBe(false));
    await act(async () => {
      await result.current.openRun("run-1");
    });

    act(() => result.current.openDeclare());
    const chosen = result.current.declareForm.on;
    await act(async () => {
      await result.current.submitDeclare();
    });

    expect(declareMock).toHaveBeenCalledWith("run-1", chosen);
    expect(result.current.feedback.success).toMatch(/declared and the fiscal year closed/);
  });

  it("records a payout for every pending allocation by default", async () => {
    const { result } = renderHook(() => useDividendsPage(PERMISSIONS));
    await waitFor(() => expect(result.current.loading).toBe(false));
    await act(async () => {
      await result.current.openRun("run-1");
    });

    act(() => result.current.openPayout());
    expect(result.current.payoutForm.open).toBe(true);
    expect(result.current.payoutForm.method).toBe("bank");
    expect(result.current.payoutForm.mode).toBe("all");

    act(() => result.current.payoutForm.set({ reference: "  TRF-1  " }));
    await act(async () => {
      await result.current.submitPayout();
    });

    expect(payoutMock).toHaveBeenCalledWith(
      "run-1",
      expect.objectContaining({
        method: "bank",
        reference: "TRF-1",
        allocation_ids: undefined,
      })
    );
    expect(result.current.payoutForm.open).toBe(false);
    expect(result.current.feedback.success).toMatch(/Payout of ₦2,769\.00 recorded/);
  });

  it("sends only the selected allocations when a subset is chosen", async () => {
    const { result } = renderHook(() => useDividendsPage(PERMISSIONS));
    await waitFor(() => expect(result.current.loading).toBe(false));
    await act(async () => {
      await result.current.openRun("run-1");
    });

    act(() => result.current.toggleSelected(rowTwo));
    act(() => result.current.openPayout());
    expect(result.current.payoutForm.mode).toBe("selected");

    act(() => result.current.payoutForm.set({ reference: "TRF-2" }));
    await act(async () => {
      await result.current.submitPayout();
    });

    expect(payoutMock).toHaveBeenCalledWith(
      "run-1",
      expect.objectContaining({ allocation_ids: ["alloc-2"] })
    );
  });

  it("refuses a payout with no reference", async () => {
    const { result } = renderHook(() => useDividendsPage(PERMISSIONS));
    await waitFor(() => expect(result.current.loading).toBe(false));
    await act(async () => {
      await result.current.openRun("run-1");
    });

    act(() => result.current.openPayout());
    await act(async () => {
      await result.current.submitPayout();
    });

    expect(payoutMock).not.toHaveBeenCalled();
    expect(result.current.feedback.error).toMatch(/payment reference/);
  });

  it("searches allocations by member and resets to the first page", async () => {
    const { result } = renderHook(() => useDividendsPage(PERMISSIONS));
    await waitFor(() => expect(result.current.loading).toBe(false));
    await act(async () => {
      await result.current.openRun("run-1");
    });

    act(() => result.current.setSearch("Adaeze"));
    await act(async () => {
      await result.current.applySearch();
    });

    expect(allocationsMock).toHaveBeenLastCalledWith(
      "run-1",
      expect.objectContaining({ q: "Adaeze", skip: 0 })
    );
    expect(result.current.appliedSearch).toBe("Adaeze");

    await act(async () => {
      await result.current.applySearch("");
    });
    expect(allocationsMock).toHaveBeenLastCalledWith(
      "run-1",
      expect.objectContaining({ q: undefined, skip: 0 })
    );
  });

  it("deletes a draft from its confirmation", async () => {
    deleteMock.mockResolvedValue(undefined);
    runsMock.mockResolvedValue([]);

    const { result } = renderHook(() => useDividendsPage(PERMISSIONS));
    await waitFor(() => expect(result.current.loading).toBe(false));

    act(() => result.current.setDeleteTarget(makeRun({ status: "draft" })));
    await act(async () => {
      await result.current.confirmDelete();
    });

    expect(deleteMock).toHaveBeenCalledWith("run-1");
    expect(result.current.deleteTarget).toBeNull();
    expect(result.current.feedback.success).toMatch(/Draft dividend run for 2025 deleted/);
  });

  it("recomputes a draft against the current settings", async () => {
    detailMock.mockResolvedValue(makeDetail(makeRun({ status: "draft", note: "Committee" })));
    recomputeMock.mockResolvedValue(makeRun({ status: "draft" }));

    const { result } = renderHook(() => useDividendsPage(PERMISSIONS));
    await waitFor(() => expect(result.current.loading).toBe(false));
    await act(async () => {
      await result.current.openRun("run-1");
    });

    await act(async () => {
      await result.current.recompute();
    });

    expect(recomputeMock).toHaveBeenCalledWith("run-1", "Committee");
    expect(result.current.feedback.success).toMatch(/recomputed/);
  });

  it("opens the manifest once the server has produced it", async () => {
    manifestMock.mockResolvedValue({
      fiscal_year: 2025,
      reference: "dividend-2025",
      rows: [
        {
          psn: "PSN-0001",
          name: "Adaeze Okafor",
          bank_name: "Zenith",
          account_number: "0123456789",
          gross_amount: "1661.40",
          withholding_amount: "0",
          net_amount: "1661.40",
          payout_id: null,
        },
      ],
      total_gross: "1661.40",
      total_withholding: "0",
      total_net: "1661.40",
    });

    const { result } = renderHook(() => useDividendsPage(PERMISSIONS));
    await waitFor(() => expect(result.current.loading).toBe(false));
    await act(async () => {
      await result.current.openRun("run-1");
    });

    await act(async () => {
      await result.current.openManifest();
    });

    expect(manifestMock).toHaveBeenCalledWith("run-1");
    expect(result.current.manifest.open).toBe(true);
    expect(result.current.manifest.data?.reference).toBe("dividend-2025");
  });
});
