import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type { LoanFeePaymentWithDetails } from "@/lib/api";

import FeePaymentsTable from "./index";

const base = {
  id: "fee-1",
  loan_id: "loan-1",
  member_id: "member-1",
  member_name: "Ada Obi",
  member_psn: "MCT-0001",
  loan_type_name: "Quick Loan",
  amount: "500.00",
  payment_reference: "TRF-1",
  receipt_content_type: "image/png",
  status: "awaiting_verification",
  created_at: "2026-11-20T10:00:00",
  updated_at: "2026-11-20T10:00:00",
} as unknown as LoanFeePaymentWithDetails;

describe("FeePaymentsTable", () => {
  it("labels each status and routes review clicks to the payment", async () => {
    const onReview = vi.fn();
    const user = userEvent.setup();

    render(
      <FeePaymentsTable
        table={{
          items: [
            base,
            { ...base, id: "fee-2", status: "verified" },
            { ...base, id: "fee-3", status: "rejected" },
          ],
          onReview,
        }}
      />
    );

    expect(screen.getByText("Awaiting verification")).toBeInTheDocument();
    expect(screen.getByText("Verified")).toBeInTheDocument();
    expect(screen.getByText("Rejected")).toBeInTheDocument();

    await user.click(screen.getAllByRole("button", { name: "Review" })[2]);
    expect(onReview).toHaveBeenCalledWith("fee-3");
  });

  it("keeps a conflicted payment readable but marked", () => {
    render(
      <FeePaymentsTable
        table={{ items: [{ ...base, conflicted: true }], onReview: vi.fn() }}
      />
    );

    expect(screen.getByText("⚠ conflict")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Review" })).toBeInTheDocument();
  });

  it("says so when the queue is empty", () => {
    render(<FeePaymentsTable table={{ items: [], onReview: vi.fn() }} />);
    expect(screen.getByText("Nothing to review.")).toBeInTheDocument();
  });
});
