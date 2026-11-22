import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type { Loan } from "@/lib/api";

import type { DashboardPageModel } from "../hooks/useDashboardPage";
import LoansSection from "./index";

const base = {
  id: "loan-1",
  loan_type_name: "Quick Loan",
  principal: "200000.00",
  monthly_installment: "33333.33",
  balance: "200000.00",
  status: "active",
  expected_end_date: "2027-05-01",
  fee_status: "due",
  fee_amount: "500.00",
  fee_rejection_reason: null,
} as unknown as Loan;

function model(items: Loan[], overrides: Record<string, unknown> = {}) {
  return {
    items,
    servicingLoanId: null,
    repayAmount: 0,
    setRepayAmount: vi.fn(),
    repayMonth: "",
    setRepayMonth: vi.fn(),
    repayReference: "",
    setRepayReference: vi.fn(),
    repayReceiptFile: null,
    setRepayReceiptFile: vi.fn(),
    startRepayment: vi.fn(),
    submitRepayment: vi.fn(),
    cancelRepayment: vi.fn(),
    feePayingLoanId: null,
    feeReference: "",
    setFeeReference: vi.fn(),
    feeReceiptFile: null,
    setFeeReceiptFile: vi.fn(),
    startFeePayment: vi.fn(),
    submitFeePayment: vi.fn(),
    cancelFeePayment: vi.fn(),
    ...overrides,
  } as DashboardPageModel["loans"];
}

describe("LoansSection fee handling", () => {
  it("offers a fee payment only while the fee is due or was rejected", () => {
    render(
      <LoansSection
        loans={model([
          base,
          { ...base, id: "loan-2", fee_status: "awaiting_verification" },
          { ...base, id: "loan-3", fee_status: "paid" },
          { ...base, id: "loan-4", fee_status: "not_required" },
        ])}
      />
    );

    expect(screen.getAllByRole("button", { name: "Pay fee" })).toHaveLength(1);
    expect(screen.getByText("Awaiting verification")).toBeInTheDocument();
    expect(screen.getByText("Paid")).toBeInTheDocument();
  });

  it("labels a rejected fee with its reason and offers a resubmission", () => {
    render(
      <LoansSection
        loans={model([
          {
            ...base,
            fee_status: "rejected",
            fee_rejection_reason: "Receipt unreadable",
          },
        ])}
      />
    );

    expect(screen.getByText(/Rejected/)).toBeInTheDocument();
    expect(screen.getByText("Receipt unreadable")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Resubmit fee" })).toBeInTheDocument();
  });

  it("starts the fee form for the chosen loan", async () => {
    const startFeePayment = vi.fn();
    const user = userEvent.setup();

    render(<LoansSection loans={model([base], { startFeePayment })} />);

    await user.click(screen.getByRole("button", { name: "Pay fee" }));
    expect(startFeePayment).toHaveBeenCalledWith(base);
  });

  it("takes the fee action away from a conflicted row", () => {
    render(<LoansSection loans={model([{ ...base, conflicted: true }])} />);
    expect(screen.queryByRole("button", { name: "Pay fee" })).not.toBeInTheDocument();
  });
});
