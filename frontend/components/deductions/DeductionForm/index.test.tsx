import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type { Member } from "@/lib/api";

import type { DeductionPrefill, DeductionsPageModel } from "../hooks/useDeductionsPage";
import DeductionForm from "./index";

function makePrefill(overrides: Partial<DeductionPrefill> = {}): DeductionPrefill {
  return {
    memberId: "member-1",
    memberName: "Test Member",
    memberStatus: "financial",
    month: "2026-11",
    contribution: "5000.00",
    loanLines: [{ loanId: "loan-1", label: "Regular loan", amount: "1000.00" }],
    conflicted: false,
    ...overrides,
  };
}

function renderForm({
  prefill = null,
  members = [],
}: {
  prefill?: DeductionPrefill | null;
  members?: Member[];
} = {}) {
  const save = vi.fn();
  const close = vi.fn();
  const form = {
    open: true,
    editing: null,
    prefill,
    members,
    loansForMember: vi.fn(() => []),
    openCreate: vi.fn(),
    openEdit: vi.fn(),
    close,
    save,
  } as unknown as DeductionsPageModel["form"];
  render(<DeductionForm form={form} busy={false} />);
  return { save, close };
}

describe("DeductionForm queue prefill", () => {
  it("opens filled with the server's expected amounts and saves them", async () => {
    const user = userEvent.setup();
    const { save } = renderForm({ prefill: makePrefill() });

    expect(screen.getByRole("heading", { name: "Enter deduction — Test Member" })).toBeInTheDocument();
    expect((screen.getByLabelText("Monthly contribution") as HTMLInputElement).value).toBe("5000.00");
    expect((screen.getByLabelText("Repayment for Regular loan") as HTMLInputElement).value).toBe("1000.00");
    // The queue fixes the member and month; the officer records, not picks.
    expect(screen.getByLabelText("Member")).toBeDisabled();
    expect(screen.getByLabelText("Deduction month")).toBeDisabled();

    await user.click(screen.getByRole("button", { name: "Create draft" }));

    expect(save).toHaveBeenCalledWith({
      member_id: "member-1",
      deduction_month: "2026-11",
      payroll_reference: undefined,
      note: undefined,
      lines: [
        { category: "monthly_contribution", amount: 5000 },
        { category: "loan_repayment", loan_id: "loan-1", amount: 1000 },
      ],
    });
  });

  it("locks a conflicted officer to the expected amounts but still lets them record", async () => {
    const user = userEvent.setup();
    const { save } = renderForm({ prefill: makePrefill({ conflicted: true }) });

    expect(screen.getByLabelText("Monthly contribution")).toBeDisabled();
    expect(screen.getByLabelText("Repayment for Regular loan")).toBeDisabled();
    // Discretionary 'other' lines are a money override -- hidden entirely.
    expect(screen.queryByRole("button", { name: "Add other deduction" })).not.toBeInTheDocument();
    expect(screen.getByText(/Conflict of interest/)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Create draft" }));

    // Recording the expectation is allowed; the backend blocks the confirm.
    expect(save).toHaveBeenCalledWith(
      expect.objectContaining({
        member_id: "member-1",
        lines: [
          { category: "monthly_contribution", amount: 5000 },
          { category: "loan_repayment", loan_id: "loan-1", amount: 1000 },
        ],
      })
    );
  });

  it("hides the contribution field for a non-financial member", () => {
    renderForm({
      prefill: makePrefill({ memberStatus: "non_financial", contribution: "" }),
    });

    expect(screen.queryByLabelText("Monthly contribution")).not.toBeInTheDocument();
    expect(screen.getByText(/Non-financial member/)).toBeInTheDocument();
    // They can still owe a loan instalment from before they exited.
    expect((screen.getByLabelText("Repayment for Regular loan") as HTMLInputElement).value).toBe("1000.00");
  });

  it("keeps blank entry editable with discretionary other lines", () => {
    renderForm();

    expect(screen.getByRole("heading", { name: "New deduction" })).toBeInTheDocument();
    expect(screen.getByLabelText("Member")).not.toBeDisabled();
    expect(screen.getByLabelText("Deduction month")).not.toBeDisabled();
    expect(screen.getByRole("button", { name: "Add other deduction" })).toBeInTheDocument();
  });
});