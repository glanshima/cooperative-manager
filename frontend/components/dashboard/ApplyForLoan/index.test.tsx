import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type { LoanType, Member } from "@/lib/api";
import { EMPTY_APPLICATION_FORM } from "../hooks/useDashboardPage";
import type { DashboardPageModel } from "../hooks/useDashboardPage";
import ApplyForLoan from ".";

const loanType: LoanType = {
  id: "type-1",
  name: "Emergency loan",
  description: "Short-term support",
  interest_rate: "0.1000",
  tenure_months: 6,
  flat_charge: "99.00",
  interest_mode: "spread_first_months",
  interest_spread_months: 3,
  is_active: true,
  open_for_application: true,
  created_at: "2026-11-01T00:00:00Z",
  updated_at: "2026-11-01T00:00:00Z",
};

const member = {
  id: "member-1",
  bank_name: "Local Bank",
  account_number: "1234567890",
} as Member;

function makeApply(overrides: Partial<DashboardPageModel["apply"]> = {}): DashboardPageModel["apply"] {
  return {
    showForm: true,
    toggle: vi.fn(),
    step: 1,
    goToStep: vi.fn(),
    error: null,
    submitting: false,
    form: { ...EMPTY_APPLICATION_FORM, loan_type_id: loanType.id, requested_amount: 1000 },
    setField: vi.fn(),
    receiptFile: null,
    setReceiptFile: vi.fn(),
    submit: vi.fn((event) => event.preventDefault()),
    applyableTypes: [loanType],
    selectedType: loanType,
    preview: {
      tenure: 6,
      mode: "spread_first_months",
      spreadMonths: 3,
      interest: 100,
      fee: 2500,
      netDisbursed: 1000,
      totalRepayable: 1100,
      installment: 166.67,
      interestInstallment: 33.33,
    },
    ...overrides,
  };
}

describe("ApplyForLoan wizard", () => {
  it("starts with the request and shows one universal fee, not the legacy type charge", () => {
    render(<ApplyForLoan apply={makeApply()} member={member} />);

    expect(screen.getByRole("heading", { name: "Loan request" })).toBeInTheDocument();
    expect(screen.getByRole("group", { name: "Loan request" })).toBeInTheDocument();
    expect(screen.getByText("One loan fee: ₦2,500.00")).toBeInTheDocument();
    expect(screen.queryByText(/99\.00/)).not.toBeInTheDocument();
    expect(screen.getAllByRole("listitem")).toHaveLength(4);
  });

  it("asks for confirmation before moving forward", async () => {
    const user = userEvent.setup();
    const apply = makeApply();
    render(<ApplyForLoan apply={apply} member={member} />);

    await user.click(screen.getByRole("button", { name: "Continue" }));

    expect(apply.goToStep).toHaveBeenCalledWith(2);
  });

  it("shows estimated terms separately from the fee on the payout step", () => {
    render(<ApplyForLoan apply={makeApply({ step: 2 })} member={member} />);

    expect(screen.getByRole("group", { name: "Terms and payout" })).toBeInTheDocument();
    expect(screen.getByText("Spread over the first months")).toBeInTheDocument();
    expect(screen.getByText("₦1,000.00")).toBeInTheDocument();
    expect(screen.getByText(/₦2,500.00 loan fee is paid separately/)).toBeInTheDocument();
    expect(screen.getByLabelText(/Send funds to my account on file/)).toBeChecked();
  });

  it("collects the transfer reference and receipt on the fee step", async () => {
    const user = userEvent.setup();
    const apply = makeApply({ step: 3 });
    render(<ApplyForLoan apply={apply} member={member} />);

    expect(screen.getByText("Loan fee due before review")).toBeInTheDocument();
    expect(screen.getByLabelText("Bank transfer reference")).toBeInTheDocument();
    const file = new File(["receipt"], "receipt.png", { type: "image/png" });
    await user.upload(screen.getByLabelText(/Payment receipt/), file);
    expect(apply.setReceiptFile).toHaveBeenCalledWith(file);
  });

  it("reviews the request, payout and paid fee before the only submit action", async () => {
    const user = userEvent.setup();
    const apply = makeApply({
      step: 4,
      form: {
        ...EMPTY_APPLICATION_FORM,
        loan_type_id: loanType.id,
        requested_amount: 1000,
        payment_reference: "TRF-123",
      },
      receiptFile: new File(["receipt"], "receipt.png", { type: "image/png" }),
    });
    render(<ApplyForLoan apply={apply} member={member} />);

    expect(screen.getByRole("group", { name: "Review and submit" })).toBeInTheDocument();
    expect(screen.getByText("Fee recorded with this application")).toBeInTheDocument();
    expect(screen.getByText("TRF-123")).toBeInTheDocument();
    expect(screen.getByText("receipt.png")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Submit application" }));
    expect(apply.submit).toHaveBeenCalledOnce();
  });

  it("shows step validation errors next to the form controls", () => {
    render(<ApplyForLoan apply={makeApply({ error: "Enter your bank transfer reference." })} member={member} />);

    expect(screen.getByRole("alert")).toHaveTextContent("Enter your bank transfer reference.");
  });
});
