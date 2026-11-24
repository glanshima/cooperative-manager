import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { CashbookPageModel } from "../hooks/useCashbookPage";
import { emptyJournal } from "../journal";
import JournalPanel from "./index";

function renderPanel({ entryDate = "2026-11-15", locked = true } = {}) {
  const model = {
    entries: { items: [], total: 0, skip: 0, limit: 25 },
    entriesLoading: false,
    accounts: [],
    activeAccounts: [],
    overview: { enabled: true, opened: true, current_month_locked: locked },
    filters: {
      value: { start: "", end: "", source: "", accountId: "", q: "" },
      change: vi.fn(),
      reset: vi.fn(),
    },
    permissions: { canPost: true, canReverse: true },
    entry: {
      open: true,
      entryDate,
      narration: "Test entry",
      reference: "",
      lines: emptyJournal(),
      set: vi.fn(),
      submit: vi.fn(),
    },
    reversal: {
      value: null,
      request: vi.fn(),
      setReason: vi.fn(),
      cancel: vi.fn(),
      submit: vi.fn(),
    },
    locks: locked ? [{ period_start: "2026-11-01", locked_at: null, note: null }] : [],
    busy: false,
    paging: { goToPage: vi.fn() },
  } as unknown as CashbookPageModel;

  render(<JournalPanel model={model} />);
  return { submit: model.entry.submit };
}

describe("JournalPanel lock guard", () => {
  it("warns that the chosen month is locked and blocks posting", () => {
    renderPanel();

    expect(screen.getByText(/November 2026 is locked/)).toBeInTheDocument();
    const post = screen.getByRole("button", { name: "Post entry" });
    expect(post).toBeDisabled();
    expect(post).toHaveAttribute("aria-describedby", "entry-locked-warning");
  });

  it("allows posting once the date is in an open month", () => {
    renderPanel({ entryDate: "2026-12-05" });

    expect(screen.queryByText(/is locked, so this entry cannot be posted/)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Post entry" })).toBeEnabled();
  });
});
