import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type { Loan, Member, PayrollDeduction } from "@/lib/api";

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

const EDITING_DRAFT = {
  id: "ded-1",
  member_id: "member-1",
  member_name: "Ada Obi",
  member_psn: "PSN-1",
  deduction_month: "2026-11-01",
  status: "draft",
  payroll_reference: "PAY-2026-11",
  note: "Carried over",
  lines: [
    { id: "l1", category: "monthly_contribution", amount: "5000.00" },
    {
      id: "l2",
      category: "loan_repayment",
      loan_id: "loan-1",
      loan_type_name: "Regular loan",
      amount: "1000.00",
    },
    {
      id: "l3",
      category: "loan_arrears",
      loan_id: "loan-1",
      loan_type_name: "Regular loan",
      amount: "600.00",
    },
  ],
} as unknown as PayrollDeduction;

function renderForm({
  prefill = null,
  editing = null,
  members = [],
  loans = [],
  busy = false,
}: {
  prefill?: DeductionPrefill | null;
  editing?: PayrollDeduction | null;
  members?: Member[];
  loans?: Loan[];
  busy?: boolean;
} = {}) {
  const save = vi.fn();
  const close = vi.fn();
  const form = {
    open: true,
    editing,
    prefill,
    members,
    loansForMember: vi.fn(() => loans),
    openCreate: vi.fn(),
    openEdit: vi.fn(),
    close,
    save,
  } as unknown as DeductionsPageModel["form"];
  const view = render(<DeductionForm form={form} busy={busy} />);
  return { save, close, unmount: view.unmount };
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

describe("DeductionForm modal", () => {
  it("renders as a labelled modal dialog with a close button", () => {
    renderForm();

    const dialog = screen.getByRole("dialog");
    expect(dialog).toHaveAttribute("aria-modal", "true");
    expect(dialog).toHaveAccessibleName("New deduction");
    expect(screen.getByRole("button", { name: "Close deduction form" })).toBeInTheDocument();
    expect(screen.getByText(/Closing this form discards/)).toBeInTheDocument();
  });

  it("closes from the close button", async () => {
    const user = userEvent.setup();
    const { close } = renderForm();

    await user.click(screen.getByRole("button", { name: "Close deduction form" }));
    expect(close).toHaveBeenCalledTimes(1);
  });

  it("closes on Escape", async () => {
    const user = userEvent.setup();
    const { close, save } = renderForm();

    await user.keyboard("{Escape}");
    expect(close).toHaveBeenCalledTimes(1);
    expect(save).not.toHaveBeenCalled();
  });

  it("closes on a backdrop click but ignores clicks inside the dialog", async () => {
    const user = userEvent.setup();
    const { close } = renderForm();

    await user.click(screen.getByRole("dialog"));
    expect(close).not.toHaveBeenCalled();

    fireEvent.click(screen.getByTestId("deduction-modal-backdrop"));
    expect(close).toHaveBeenCalledTimes(1);
  });

  it("moves focus into the dialog and restores it to the opener on close", () => {
    const opener = document.createElement("button");
    opener.textContent = "Open form";
    document.body.appendChild(opener);
    opener.focus();

    const { unmount } = renderForm();

    expect(screen.getByLabelText("Member")).toHaveFocus();

    unmount();

    expect(opener).toHaveFocus();
    opener.remove();
  });

  it("keeps the dialog open while a save is in flight", async () => {
    const user = userEvent.setup();
    const { close } = renderForm({ busy: true });

    const closeButton = screen.getByRole("button", { name: "Close deduction form" });
    expect(closeButton).toBeDisabled();
    expect(screen.getByRole("button", { name: "Create draft" })).toBeDisabled();

    await user.keyboard("{Escape}");
    fireEvent.click(screen.getByTestId("deduction-modal-backdrop"));
    expect(close).not.toHaveBeenCalled();
  });

  it("keeps validation errors inside the open dialog", async () => {
    const user = userEvent.setup();
    const { save, close } = renderForm();

    await user.click(screen.getByRole("button", { name: "Create draft" }));

    expect(screen.getByText("Choose a member.")).toBeInTheDocument();
    expect(save).not.toHaveBeenCalled();
    expect(close).not.toHaveBeenCalled();
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });
});

describe("DeductionForm editing", () => {
  it("keeps an existing arrears line when editing a draft", async () => {
    const user = userEvent.setup();
    const { save } = renderForm({ editing: EDITING_DRAFT, loans: [ACTIVE_LOAN] });

    expect(screen.getByRole("dialog")).toHaveAccessibleName("Edit draft deduction");
    expect((screen.getByLabelText("Monthly contribution") as HTMLInputElement).value).toBe(
      "5000.00"
    );
    expect(
      (screen.getByLabelText("Repayment for Regular loan") as HTMLInputElement).value
    ).toBe("1000.00");
    // The arrears line already on the draft must survive an edit, not turn
    // into an optional catch-up the officer has to re-add.
    expect(
      (screen.getByLabelText("Arrears catch-up for Regular loan") as HTMLInputElement).value
    ).toBe("600.00");

    await user.click(screen.getByRole("button", { name: "Save draft" }));

    expect(save).toHaveBeenCalledWith(
      {
        deduction_month: "2026-11",
        payroll_reference: "PAY-2026-11",
        note: "Carried over",
        lines: [
          { category: "monthly_contribution", amount: 5000 },
          { category: "loan_repayment", loan_id: "loan-1", amount: 1000 },
          { category: "loan_arrears", loan_id: "loan-1", amount: 600 },
        ],
      },
      "ded-1"
    );
  });
});