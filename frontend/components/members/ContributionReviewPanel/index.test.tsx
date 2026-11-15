import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type { ContributionChangeRequest } from "@/lib/api/contributions";

import ContributionReviewPanel from ".";

const pendingRequest = {
  id: "req-1",
  member_id: "member-1",
  member_name: "Ada Obi",
  member_psn: "MCT-0001",
  current_amount: "5000.00",
  requested_amount: "8000.00",
  reason: "Salary increase",
  status: "pending",
  effective_from: null,
  requested_by_user_id: "user-9",
  reviewed_by_user_id: null,
  reviewed_at: null,
  review_reason: null,
  created_at: "2026-11-01T00:00:00Z",
  updated_at: "2026-11-01T00:00:00Z",
  conflicted: false,
} as ContributionChangeRequest;

function renderPanel() {
  const handlers = {
    onRefresh: vi.fn(),
    onApprove: vi.fn().mockResolvedValue(true),
    onReject: vi.fn().mockResolvedValue(true),
  };
  render(<ContributionReviewPanel requests={[pendingRequest]} loading={false} {...handlers} />);
  return handlers;
}

describe("ContributionReviewPanel", () => {
  it("asks before approving and sends the decision only on confirm", async () => {
    const handlers = renderPanel();

    await userEvent.click(screen.getByRole("button", { name: "Approve" }));
    expect(handlers.onApprove).not.toHaveBeenCalled();

    const dialog = screen.getByRole("dialog", { name: "Approve contribution change?" });
    expect(dialog).toHaveTextContent("₦8,000.00");

    await userEvent.click(within(dialog).getByRole("button", { name: "Approve" }));

    expect(handlers.onApprove).toHaveBeenCalledWith("req-1", "");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("requires a reason and shows it in the rejection confirmation", async () => {
    const handlers = renderPanel();

    const reject = screen.getByRole("button", { name: "Reject" });
    expect(reject).toBeDisabled();

    await userEvent.type(
      screen.getByPlaceholderText("Review reason (required to reject)"),
      "Above the agreed cap"
    );
    await userEvent.click(reject);

    const dialog = screen.getByRole("dialog", { name: "Reject contribution change?" });
    expect(dialog).toHaveTextContent("Above the agreed cap");
    expect(handlers.onReject).not.toHaveBeenCalled();

    await userEvent.click(within(dialog).getByRole("button", { name: "Reject" }));

    expect(handlers.onReject).toHaveBeenCalledWith("req-1", "Above the agreed cap");
  });

  it("sends nothing when the confirmation is cancelled", async () => {
    const handlers = renderPanel();

    await userEvent.click(screen.getByRole("button", { name: "Approve" }));
    await userEvent.click(
      within(screen.getByRole("dialog")).getByRole("button", { name: "Cancel" })
    );

    expect(handlers.onApprove).not.toHaveBeenCalled();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
});
