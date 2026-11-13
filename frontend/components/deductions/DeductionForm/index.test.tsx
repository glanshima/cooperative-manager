import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type { Loan, Member } from "@/lib/api";

import type { DeductionPrefill, DeductionsPageModel } from "../hooks/useDeductionsPage";
import DeductionForm from "./index";

function makePrefill(overrides: Partial<DeductionPrefill> = {}): DeductionPrefill {
  return {
    memberId: "member-1",
    memberName: "Test Member",
    memberStatus: "financial",
    month: "2026-11",
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
    ],
    conflicted: false,
    ...overrides,
  };
}

const ACTIVE_LOAN = {
  id: "loan-1",
  member_id: "member-1",
  loan_type_name: "Regular loan",
  balance: "9000.00",
  status: "active",
} as unknown as Loan;

function renderForm({
  prefill = null,
  members = [],
  loans = [],
}: {
  prefill?: DeductionPrefill | null;
  members?: Member[];
  loans?: Loan[];
} = {}) {
  const save = vi.fn();
  const close = vi.fn();
  const form = {
    open: true,
    editing: null,
    prefill,
    members,
    loansForMember: vi.fn(() => loans),
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

  it("splits a queued catch-up into its own editable line beside the instalment", async () => {
    const user = userEvent.setup();
    const { save } = renderForm({
      prefill: makePrefill({
        loanLines: [
          ...makePrefill().loanLines,
          {
            key: "loan-1:loan_arrears",
            loanId: "loan-1",
            category: "loan_arrears",
            loanName: "Regular loan",
            label: "Arrears on Regular loan — 6 months behind",
            amount: "6000.00",
          },
        ],
      }),
    });

    expect((screen.getByLabelText("Repayment for Regular loan") as HTMLInputElement).value).toBe(
      "1000.00"
    );
    expect(screen.getByText("Arrears on Regular loan — 6 months behind")).toBeInTheDocument();
    const catchUp = screen.getByLabelText("Arrears catch-up for Regular loan") as HTMLInputElement;
    expect(catchUp.value).toBe("6000.00");
    // The queue already decided the loan needs a catch-up; no button to add one.
    expect(
      screen.queryByRole("button", { name: "Add arrears catch-up" })
    ).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Create draft" }));

    expect(save).toHaveBeenCalledWith(
      expect.objectContaining({
        lines: [
          { category: "monthly_contribution", amount: 5000 },
          { category: "loan_repayment", loan_id: "loan-1", amount: 1000 },
          { category: "loan_arrears", loan_id: "loan-1", amount: 6000 },
        ],
      })
    );
  });

  it("locks a queued catch-up too when the officer is conflicted", () => {
    renderForm({
      prefill: makePrefill({
        conflicted: true,
        loanLines: [
          ...makePrefill().loanLines,
          {
            key: "loan-1:loan_arrears",
            loanId: "loan-1",
            category: "loan_arrears",
            loanName: "Regular loan",
            label: "Arrears on Regular loan — 6 months behind",
            amount: "6000.00",
          },
        ],
      }),
    });

    expect(screen.getByLabelText("Arrears catch-up for Regular loan")).toBeDisabled();
  });

  it("lets a manual entry open a catch-up row for a loan of its own", async () => {
    const user = userEvent.setup();
    const member = { id: "member-1", psn: "PSN-1", name: "Test Member", status: "financial" };
    const { save } = renderForm({
      members: [member as unknown as Member],
      loans: [ACTIVE_LOAN],
    });

    await user.selectOptions(screen.getByLabelText("Member"), "member-1");
    await user.click(screen.getByRole("button", { name: "Add arrears catch-up" }));

    const catchUp = screen.getByLabelText("Arrears catch-up for Regular loan") as HTMLInputElement;
    await user.type(catchUp, "2500");
    await user.type(
      screen.getByLabelText("Repayment for Regular loan") as HTMLInputElement,
      "1000"
    );
    await user.click(screen.getByRole("button", { name: "Create draft" }));

    expect(save).toHaveBeenCalledWith(
      expect.objectContaining({
        member_id: "member-1",
        lines: [
          { category: "loan_repayment", loan_id: "loan-1", amount: 1000 },
          { category: "loan_arrears", loan_id: "loan-1", amount: 2500 },
        ],
      })
    );
  });
});