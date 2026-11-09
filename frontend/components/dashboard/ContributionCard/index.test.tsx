import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { Member } from "@/lib/api";
import {
  createContributionChangeRequest,
  getMyContributionChangeRequests,
} from "@/lib/api/contributions";

import ContributionCard from "./index";

vi.mock("@/lib/api/contributions", () => ({
  getMyContributionChangeRequests: vi.fn(),
  createContributionChangeRequest: vi.fn(),
}));

const getRequestsMock = vi.mocked(getMyContributionChangeRequests);
const createMock = vi.mocked(createContributionChangeRequest);

const financialMember = {
  id: "member-1",
  psn: "MCT-0001",
  name: "Ada Obi",
  status: "financial",
  monthly_contribution_amount: "5000.00",
} as unknown as Member;

describe("ContributionCard", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    getRequestsMock.mockResolvedValue([]);
  });

  it("shows a financial member's amount and loads their requests on mount", async () => {
    render(<ContributionCard member={financialMember} />);

    expect(screen.getByText("₦5,000.00")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Request change" })).toBeInTheDocument();
    await waitFor(() => expect(getRequestsMock).toHaveBeenCalledTimes(1));
  });

  it("tells a non-financial member they have no monthly contribution", async () => {
    render(<ContributionCard member={{ ...financialMember, status: "non_financial" } as Member} />);

    expect(screen.getByText(/Non-financial members/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Request change" })).not.toBeInTheDocument();
    await waitFor(() => expect(getRequestsMock).toHaveBeenCalled());
  });

  it("points a member with no amount on file to an officer", async () => {
    render(
      <ContributionCard member={{ ...financialMember, monthly_contribution_amount: null } as Member} />
    );

    expect(screen.getByText(/not yet set/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Request change" })).not.toBeInTheDocument();
    await waitFor(() => expect(getRequestsMock).toHaveBeenCalled());
  });

  it("disables requesting while a change is already pending", async () => {
    getRequestsMock.mockResolvedValue([
      { id: "req-1", status: "pending", current_amount: "5000.00", requested_amount: "8000.00" } as any,
    ]);
    render(<ContributionCard member={financialMember} />);

    const button = await screen.findByRole("button", { name: "Request pending" });
    expect(button).toBeDisabled();
  });

  it("submits a change request with the amount and reason", async () => {
    createMock.mockResolvedValue({} as any);
    render(<ContributionCard member={financialMember} />);
    await waitFor(() => expect(getRequestsMock).toHaveBeenCalled());

    fireEvent.click(screen.getByRole("button", { name: "Request change" }));
    expect(screen.getByText("Request contribution change")).toBeInTheDocument();

    fireEvent.change(screen.getByPlaceholderText("e.g. 8000.00"), { target: { value: "8000" } });
    fireEvent.change(
      screen.getByPlaceholderText("e.g. Salary increase, need to increase savings"),
      { target: { value: "Salary increase" } }
    );
    fireEvent.submit(screen.getByRole("button", { name: "Submit request" }).closest("form")!);

    await waitFor(() =>
      expect(createMock).toHaveBeenCalledWith({ requested_amount: 8000, reason: "Salary increase" })
    );
  });
});