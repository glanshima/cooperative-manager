import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type {
  DeductionWorklistEntryState,
  DeductionWorklistItem,
  DeductionWorklistOut,
} from "@/lib/api";

import type { DeductionsPageModel } from "../hooks/useDeductionsPage";
import DeductionWorklist from "./index";

function makeItem(overrides: Partial<DeductionWorklistItem> = {}): DeductionWorklistItem {
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
        arrears: "0.00",
        months_behind: 0,
      },
    ],
    warnings: [],
    expected_total: "6000.00",
    deduction_id: null,
    deduction_status: null,
    conflicted: false,
    ...overrides,
  };
}

function makeWorklistOut(
  items: DeductionWorklistItem[],
  entryState: DeductionWorklistEntryState,
  overrides: Partial<DeductionWorklistOut> = {}
): DeductionWorklistOut {
  // The month-wide counts come from the server; a page of items only tells
  // the test how many of THIS page are entered.
  const entered = items.filter((item) => item.deduction_id).length;
  const pending = items.length - entered;
  return {
    month: "2026-11-01",
    items,
    total: items.length,
    skip: 0,
    limit: 20,
    entry_state: entryState,
    due_count: pending + entered,
    pending_count: pending,
    entered_count: entered,
    expected_total: "6000.00",
    ...overrides,
  };
}

function renderWorklist({
  items = [makeItem()],
  entryState = "pending" as DeductionWorklistEntryState,
  lastEntered = null,
  error = null,
  dataOverrides = {},
}: {
  items?: DeductionWorklistItem[];
  entryState?: DeductionWorklistEntryState;
  lastEntered?: { id: string; memberName: string } | null;
  error?: string | null;
  dataOverrides?: Partial<DeductionWorklistOut>;
} = {}) {
  const data = makeWorklistOut(items, entryState, dataOverrides);
  const openItem = vi.fn();
  const undo = vi.fn();
  const setEntryState = vi.fn();
  const goToPage = vi.fn();
  const onPageSizeChange = vi.fn();
  const onAddAny = vi.fn();
  const worklist = {
    data,
    loading: false,
    error,
    entryState,
    setEntryState,
    refresh: vi.fn(),
    openItem,
    lastEntered,
    undo,
    pagination: { skip: data.skip, limit: data.limit, total: data.total, goToPage },
  } as unknown as DeductionsPageModel["worklist"];
  render(
    <DeductionWorklist
      worklist={worklist}
      month="2026-11"
      setMonth={vi.fn()}
      onAddAny={onAddAny}
      onPageSizeChange={onPageSizeChange}
      busy={false}
    />
  );
  return { openItem, undo, setEntryState, goToPage, onPageSizeChange, onAddAny };
}

describe("DeductionWorklist", () => {
  it("lists a due member with expected lines and opens the form on Enter", async () => {
    const user = userEvent.setup();
    const item = makeItem();
    const { openItem } = renderWorklist({ items: [item] });

    expect(screen.getByText(/Test Member · PSN PSN-1/)).toBeInTheDocument();
    expect(screen.getByText(/Contribution/)).toBeInTheDocument();
    expect(screen.getByText(/Regular loan/)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Enter" }));
    expect(openItem).toHaveBeenCalledWith(item);
  });

  it("flags a conflicted member and offers expected-amounts entry", () => {
    renderWorklist({ items: [makeItem({ conflicted: true })] });

    expect(screen.getByText("⚠ conflict")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Enter expected amounts" })).toBeInTheDocument();
  });

  it("shows an entered member as a badge with no Enter button", () => {
    renderWorklist({
      entryState: "entered",
      items: [makeItem({ deduction_id: "ded-1", deduction_status: "draft" })],
    });

    expect(screen.getByText(/Entered · Draft/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Enter" })).not.toBeInTheDocument();
  });

  it("annotates a loan line with arrears when months are behind", () => {
    renderWorklist({
      items: [
        makeItem({
          lines: [
            {
              category: "loan_repayment",
              amount: "1000.00",
              loan_id: "loan-1",
              loan_type_name: "Regular loan",
              arrears: "2000.00",
              months_behind: 2,
            },
          ],
        }),
      ],
    });

    expect(screen.getByText(/arrears/)).toBeInTheDocument();
    expect(screen.getByText(/2 months/)).toBeInTheDocument();
  });

  it("offers a one-click undo right after an entry", async () => {
    const user = userEvent.setup();
    const { undo } = renderWorklist({
      items: [],
      lastEntered: { id: "ded-1", memberName: "Test Member" },
    });

    const banner = screen.getByRole("status");
    expect(banner).toHaveTextContent("Entered Test Member.");
    await user.click(screen.getByRole("button", { name: "Undo" }));
    expect(undo).toHaveBeenCalled();
  });

  it("switches segments from the control and marks the open one pressed", async () => {
    const user = userEvent.setup();
    const { setEntryState } = renderWorklist();

    expect(screen.getByRole("button", { name: "Pending (1)" })).toHaveAttribute(
      "aria-pressed",
      "true"
    );
    expect(screen.getByRole("button", { name: "Entered (0)" })).toHaveAttribute(
      "aria-pressed",
      "false"
    );

    await user.click(screen.getByRole("button", { name: "Entered (0)" }));
    expect(setEntryState).toHaveBeenCalledWith("entered");
  });

  it("shows the month-wide counts beside the page it is holding", () => {
    renderWorklist({
      items: [makeItem({ deduction_id: "ded-1", deduction_status: "draft" })],
      entryState: "entered",
      dataOverrides: { total: 41, skip: 20, due_count: 42, pending_count: 1, entered_count: 41 },
    });

    // 42 due this month, 41 of them entered -- and the page shows one row.
    expect(screen.getByRole("button", { name: "Pending (1)" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Entered (41)" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "All (42)" })).toBeInTheDocument();
    expect(screen.getByText("Page 2 of 3")).toBeInTheDocument();
  });

  it("turns the page without leaving the segment", async () => {
    const user = userEvent.setup();
    const { goToPage } = renderWorklist({
      items: [makeItem()],
      dataOverrides: { total: 25, limit: 20 },
    });

    await user.click(screen.getByRole("button", { name: "Next" }));
    expect(goToPage).toHaveBeenCalledWith(20);
  });

  it("lets the officer choose the page size", async () => {
    const user = userEvent.setup();
    const { onPageSizeChange } = renderWorklist();

    await user.selectOptions(screen.getByLabelText("Rows per page"), "100");
    expect(onPageSizeChange).toHaveBeenCalledWith(100);
  });

  it("describes the empty page in the segment the officer is looking at", () => {
    renderWorklist({ items: [], entryState: "entered" });
    expect(screen.getByText(/Nothing has been entered for/)).toBeInTheDocument();
  });

  it("says the pending queue is finished rather than that nothing is due", () => {
    renderWorklist({
      items: [],
      dataOverrides: { due_count: 12, pending_count: 0, entered_count: 12, expected_total: "0.00" },
    });

    expect(screen.getByText(/Nothing left to enter for/)).toBeInTheDocument();
  });
});
