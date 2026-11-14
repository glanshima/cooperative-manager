import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type { PayrollDeduction } from "@/lib/api";

import DeductionsTable from "./index";

const draft = {
  id: "ded-1",
  member_id: "member-1",
  member_name: "Ada Obi",
  member_psn: "MCT-0001",
  deduction_month: "2026-11-01",
  status: "draft",
  contribution_total: "2000.00",
  loan_total: "0.00",
  arrears_total: "0.00",
  other_total: "0.00",
  grand_total: "2000.00",
  lines: [],
} as unknown as PayrollDeduction;

function renderTable(items: PayrollDeduction[], selected: string[] = [], search = "") {
  const table = {
    items,
    selected,
    loading: false,
    eligible: {
      submit: items.length,
      return_to_draft: 0,
      confirm: 0,
      not_deducted: items.length,
      void: items.length,
    },
    toggleAll: vi.fn(),
    toggleSelected: vi.fn(),
    clearSelection: vi.fn(),
    pagination: { skip: 0, limit: 50, total: items.length, goToPage: vi.fn() },
  };
  const actions = {
    request: vi.fn(),
    submitAll: {
      preview: null,
      request: vi.fn(),
      confirm: vi.fn(),
      cancel: vi.fn(),
    },
    pending: null,
    reason: "",
    setReason: vi.fn(),
    confirmPending: vi.fn(),
    cancelPending: vi.fn(),
  };
  const onEdit = vi.fn();
  render(
    <DeductionsTable table={table} actions={actions} busy={false} search={search} onEdit={onEdit} />
  );
  return { table, actions, onEdit };
}

describe("DeductionsTable", () => {
  it("offers the lifecycle actions for a normal draft", () => {
    renderTable([draft]);
    expect(screen.getByRole("button", { name: "Edit" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Submit" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Void" })).toBeInTheDocument();
  });

  it("shows a conflicted draft with no actions and no bulk selection", async () => {
    const user = userEvent.setup();
    const { table, onEdit } = renderTable([
      draft,
      { ...draft, id: "ded-2", member_psn: "0002", conflicted: true },
    ]);

    // The row is still on the ledger -- only its actions are gone.
    expect(screen.getByText("0002")).toBeInTheDocument();
    expect(screen.getAllByText("⚠ conflict")).toHaveLength(1);
    // One row still has the lifecycle actions; the conflicted one has none.
    expect(screen.getAllByRole("button", { name: "Submit" })).toHaveLength(1);
    expect(screen.getAllByRole("button", { name: "Edit" })).toHaveLength(1);
    expect(screen.getAllByRole("button", { name: "Void" })).toHaveLength(1);

    const conflictedCheckbox = screen.getByRole("checkbox", { name: "Select 0002" });
    expect(conflictedCheckbox).toBeDisabled();
    await user.click(conflictedCheckbox);
    expect(table.toggleSelected).not.toHaveBeenCalled();

    // Select-all must never queue a conflicted record for a bulk write.
    const selectAll = screen.getByRole("checkbox", { name: "Select all deductions" });
    await user.click(selectAll);
    expect(table.toggleAll).toHaveBeenCalledWith(["ded-1"]);

    expect(onEdit).not.toHaveBeenCalled();
  });

  it("explains an empty search result instead of claiming the month is empty", () => {
    renderTable([], [], "zzz");

    expect(screen.getByText(/No deduction records match “zzz”/)).toBeInTheDocument();
  });
});
