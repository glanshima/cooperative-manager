import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type { LoanApplicationWithReceipt } from "@/lib/api";
import type { LoanApplicationsPageModel } from "../hooks/useLoanApplicationsPage";

import ApplicationReviewPanel from ".";

const application = {
  id: "app-1",
  member_id: "member-1",
  loan_type_id: "type-1",
  member_name: "Ada Obi",
  member_psn: "MCT-0001",
  loan_type_name: "Capital Loan",
  requested_amount: "100000.00",
  requested_tenure_months: 12,
  preferred_disbursement_date: "2026-12-01",
  use_default_account: true,
  status: "pending",
  was_restricted_at_submission: false,
  form_fee_amount: "2500.00",
  payment_reference: "TRANSFER-001",
  payment_status: "awaiting_verification",
  receipt_content_type: "application/pdf",
  receipt_image_base64: "abc",
} as unknown as LoanApplicationWithReceipt;

function renderReview(overrides: Partial<LoanApplicationWithReceipt> = {}) {
  const review = {
    application: { ...application, ...overrides },
    form: {
      approvedAmount: "100000.00",
      setApprovedAmount: vi.fn(),
      approvedTenureMonths: "12",
      setApprovedTenureMonths: vi.fn(),
      tenureDecisionReason: "",
      setTenureDecisionReason: vi.fn(),
      adminNotes: "",
      setAdminNotes: vi.fn(),
      rejectionReason: "",
      setRejectionReason: vi.fn(),
      canReapply: true,
      setCanReapply: vi.fn(),
    },
    onVerifyPayment: vi.fn(),
    onDecide: vi.fn(),
    onDisburse: vi.fn(),
    close: vi.fn(),
  } as unknown as LoanApplicationsPageModel["review"];

  render(<ApplicationReviewPanel review={review} />);
  return review;
}

describe("ApplicationReviewPanel", () => {
  it("shows all three gates and verifies the application fee at the first gate", async () => {
    const review = renderReview();
    const user = userEvent.setup();

    expect(screen.getByRole("list", { name: "Application workflow stages" })).toBeInTheDocument();
    expect(screen.getAllByRole("listitem")).toHaveLength(3);
    expect(screen.getByText("Review and verify")).toBeInTheDocument();
    expect(screen.getByText("Approve or reject")).toBeInTheDocument();
    expect(screen.getByText("Disburse")).toBeInTheDocument();
    expect(screen.getByText("₦2,500.00")).toBeInTheDocument();
    expect(screen.getAllByText("Awaiting verification")).toHaveLength(2);
    expect(screen.queryByRole("button", { name: "Approve loan" })).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Verify payment" }));
    expect(review.onVerifyPayment).toHaveBeenCalledWith(true);
  });

  it("shows frozen approval terms and confirms the fee is not charged again", () => {
    renderReview({
      payment_status: "verified",
      status: "approved",
      approved_amount: "90000.00",
      approved_tenure_months: 10,
      approved_interest_rate: "0.1000",
      approved_interest_mode: "spread_first_months",
      approved_interest_spread_months: 3,
      tenure_decision_reason: "Shorter tenure agreed",
    });

    expect(screen.getByText("₦90,000.00")).toBeInTheDocument();
    expect(screen.getByText("10 months")).toBeInTheDocument();
    expect(screen.getByText("10.00%")).toBeInTheDocument();
    expect(screen.getByText("Spread over the first months")).toBeInTheDocument();
    expect(screen.getByText("Interest spread period")).toBeInTheDocument();
    expect(screen.getByText(/will not\s+be requested again/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Disburse now" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Approve loan" })).not.toBeInTheDocument();
  });

  it("makes legacy approval fallback explicit instead of inventing frozen terms", () => {
    renderReview({ payment_status: "verified", status: "approved" });

    expect(screen.getAllByText("Resolved at disbursement (legacy approval)")).toHaveLength(2);
    expect(screen.getByRole("button", { name: "Disburse now" })).toBeInTheDocument();
  });

  it("keeps conflicted applications readable but removes every write action", () => {
    renderReview({ conflicted: true });

    expect(screen.getByText(/actions are disabled/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Verify payment" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Reject payment" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Close application review" })).toBeInTheDocument();
  });

  it("does not offer disbursement for a rejected application", () => {
    renderReview({ payment_status: "verified", status: "rejected" });

    expect(screen.getByText("Rejected", { selector: "small" })).toBeInTheDocument();
    expect(screen.getByText(/No loan can be disbursed/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Disburse now" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Approve loan" })).not.toBeInTheDocument();
  });

  it("does not mark the loan decision complete when only payment was rejected", () => {
    renderReview({ payment_status: "rejected", status: "rejected" });

    const decisionStage = screen.getByText("Approve or reject").closest("li");
    expect(decisionStage).not.toBeNull();
    expect(within(decisionStage!).getByText("Not reached")).toBeInTheDocument();
    expect(within(decisionStage!).queryByText("✓")).not.toBeInTheDocument();
  });
});
