import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type { DeductionWorklistItem, DeductionWorklistOut } from "@/lib/api";

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

function renderWorklist({
  items = [makeItem()],
  includeEntered = false,
  lastEntered = null,
  error = null,
}: {
  items?: DeductionWorklistItem[];
  includeEntered?: boolean;
  lastEntered?: { id: string; memberName: string } | null;
  error?: string | null;
} = {}) {
  const data: DeductionWorklistOut = {
    month: "2026-11-01",
    items,
    due_count: items.filter((item) => !item.deduction_id).length,
    entered_count: items.filter((item) => item.deduction_id).length,
    expected_total: "6000.00",
  };
  const openItem = vi.fn();
  const undo = vi.fn();
  const setIncludeEntered = vi.fn();
  const onAddAny = vi.fn();
  const worklist = {
    data,
    loading: false,
    error,
    includeEntered,
    setIncludeEntered,
    refresh: vi.fn(),
    openItem,
    lastEntered,
    undo,
  } as unknown as DeductionsPageModel["worklist"];
  render(
    <DeductionWorklist
      worklist={worklist}
      month="2026-11"
      setMonth={vi.fn()}
      onAddAny={onAddAny}
      busy={false}
    />
  );
  return { openItem, undo, setIncludeEntered, onAddAny };
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

  it("toggles showing already-entered members", async () => {
    const user = userEvent.setup();
    const { setIncludeEntered } = renderWorklist();

    await user.click(screen.getByLabelText("Show already entered"));
    expect(setIncludeEntered).toHaveBeenCalledWith(true);
  });

  it("shows an empty state when nothing is due", () => {
    renderWorklist({ items: [] });
    expect(screen.getByText(/Nothing due/)).toBeInTheDocument();
  });
});