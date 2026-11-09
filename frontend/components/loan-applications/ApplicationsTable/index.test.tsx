import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type { LoanApplication } from "@/lib/api";

import ApplicationsTable from "./index";

const base = {
  id: "app-1",
  member_id: "member-1",
  member_name: "Ada Obi",
  member_psn: "MCT-0001",
  loan_type_name: "Capital Loan",
  requested_amount: "100000.00",
  payment_status: "awaiting_verification",
  status: "pending",
  was_restricted_at_submission: false,
} as unknown as LoanApplication;

const restricted = { ...base, id: "app-2", was_restricted_at_submission: true };
const approved = { ...base, id: "app-3", status: "approved" as const };
const alreadyDisbursed = {
  ...base,
  id: "app-4",
  status: "approved" as const,
  resulting_loan_id: "loan-1",
};

describe("ApplicationsTable", () => {
  it("flags restricted submissions and only offers disbursal for undisbursed approvals", () => {
    render(
      <ApplicationsTable
        table={{
          items: [base, restricted, approved, alreadyDisbursed],
          onReview: vi.fn(),
          onDisburse: vi.fn(),
        }}
      />
    );

    expect(screen.getAllByText("⚠ restricted")).toHaveLength(1);
    expect(screen.getAllByRole("button", { name: "Disburse" })).toHaveLength(1);
    expect(screen.getAllByRole("button", { name: "Review" })).toHaveLength(4);
  });

  it("routes review and disbursal clicks to the matching application", async () => {
    const onReview = vi.fn();
    const onDisburse = vi.fn();
    const user = userEvent.setup();

    render(
      <ApplicationsTable table={{ items: [base, approved], onReview, onDisburse }} />
    );

    await user.click(screen.getAllByRole("button", { name: "Review" })[1]);
    expect(onReview).toHaveBeenCalledWith("app-3");

    await user.click(screen.getByRole("button", { name: "Disburse" }));
    expect(onDisburse).toHaveBeenCalledWith("app-3");
  });

  it("keeps a conflicted application visible but takes away the write action", () => {
    const onDisburse = vi.fn();
    render(
      <ApplicationsTable
        table={{
          items: [approved, { ...approved, id: "app-5", conflicted: true }],
          onReview: vi.fn(),
          onDisburse,
        }}
      />
    );

    expect(screen.getByText("⚠ conflict")).toBeInTheDocument();
    // Review is a read, so this officer may still open it; disbursing is
    // a write, so only the unconflicted row offers it.
    expect(screen.getAllByRole("button", { name: "Review" })).toHaveLength(2);
    expect(screen.getAllByRole("button", { name: "Disburse" })).toHaveLength(1);
    expect(onDisburse).not.toHaveBeenCalled();
  });
});
