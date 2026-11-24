import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  getCashbookOverview,
  listCashbookAccounts,
  listCashbookEntries,
  listCashbookPeriodLocks,
  postCashbookOpening,
} from "@/lib/api";

import { newJournalLine } from "../journal";
import { useCashbookPage } from "./useCashbookPage";

vi.mock("@/lib/api", () => ({
  createCashbookAccount: vi.fn(),
  createCashbookEntry: vi.fn(),
  getCashbookOverview: vi.fn(),
  listCashbookAccounts: vi.fn(),
  listCashbookEntries: vi.fn(),
  listCashbookPeriodLocks: vi.fn(),
  lockCashbookPeriod: vi.fn(),
  postCashbookOpening: vi.fn(),
  reverseCashbookEntry: vi.fn(),
  unlockCashbookPeriod: vi.fn(),
  updateCashbookAccount: vi.fn(),
}));

const overviewMock = vi.mocked(getCashbookOverview);
const accountsMock = vi.mocked(listCashbookAccounts);
const entriesMock = vi.mocked(listCashbookEntries);
const locksMock = vi.mocked(listCashbookPeriodLocks);
const openingMock = vi.mocked(postCashbookOpening);

const PERMISSIONS = ["accounting.post", "accounting.view", "accounting.adjust"];

beforeEach(() => {
  vi.clearAllMocks();
  overviewMock.mockResolvedValue({
    enabled: true,
    opened: true,
    account_count: 2,
    entry_count: 0,
    cash_balance: "0",
    bank_balance: "0",
    current_month_locked: false,
    locked_periods: [],
  });
  accountsMock.mockResolvedValue([
    {
      id: "bank",
      code: "1010",
      name: "Bank",
      kind: "asset",
      is_active: true,
      debit: "0",
      credit: "0",
      balance: "0",
    },
    {
      id: "income",
      code: "4000",
      name: "Interest income",
      kind: "income",
      is_active: true,
      debit: "0",
      credit: "0",
      balance: "0",
    },
  ]);
  entriesMock.mockResolvedValue({ items: [], total: 0, skip: 0, limit: 25 });
  locksMock.mockResolvedValue([]);
});

describe("useCashbookPage", () => {
  it("loads the overview, chart, locks and first page of the journal", async () => {
    const { result } = renderHook(() => useCashbookPage(PERMISSIONS));

    await waitFor(() => expect(result.current.loading).toBe(false));

    expect(overviewMock).toHaveBeenCalled();
    expect(accountsMock).toHaveBeenCalled();
    expect(locksMock).toHaveBeenCalled();
    await waitFor(() => expect(entriesMock).toHaveBeenCalled());
    expect(result.current.overview?.opened).toBe(true);
    expect(result.current.activeAccounts).toHaveLength(2);
  });

  it("refuses to post an opening journal whose sides do not match", async () => {
    const { result } = renderHook(() => useCashbookPage(PERMISSIONS));
    await waitFor(() => expect(result.current.loading).toBe(false));

    const first = { ...newJournalLine(), accountId: "bank", debit: "100" };
    const second = { ...newJournalLine(), accountId: "income", credit: "90" };
    act(() => {
      result.current.opening.set({
        ...result.current.opening,
        open: true,
        lines: [first, second],
      });
    });

    await act(async () => {
      await result.current.opening.submit();
    });

    expect(openingMock).not.toHaveBeenCalled();
    expect(result.current.feedback.error).toMatch(/Debits and credits must match/);
  });

  it("posts a valid opening journal and closes the form", async () => {
    openingMock.mockResolvedValue({
      id: "entry",
      entry_date: "2026-11-23",
      narration: "Opening balances",
      source: "opening",
      lines: [],
    });
    const { result } = renderHook(() => useCashbookPage(PERMISSIONS));
    await waitFor(() => expect(result.current.loading).toBe(false));

    act(() => {
      result.current.opening.set({
        open: true,
        asOf: "2026-11-23",
        note: "  Go-live  ",
        lines: [
          { ...newJournalLine(), accountId: "bank", debit: "1000" },
          { ...newJournalLine(), accountId: "income", credit: "1000" },
        ],
      });
    });

    await act(async () => {
      await result.current.opening.submit();
    });

    expect(openingMock).toHaveBeenCalledWith({
      as_of: "2026-11-23",
      note: "Go-live",
      lines: [
        { account_id: "bank", debit: "1000", credit: "0" },
        { account_id: "income", debit: "0", credit: "1000" },
      ],
    });
    expect(result.current.opening.open).toBe(false);
    expect(result.current.feedback.success).toMatch(/Opening balances posted/);
  });
});
