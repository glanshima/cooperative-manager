import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type { Member } from "@/lib/api";

import MemberDetailsModal from ".";

const ada = {
  id: "member-1",
  psn: "MCT-0001",
  name: "Ada Obi",
  department: "Registry",
  phone: "08000000001",
  email: "ada@example.com",
  status: "financial",
  loan_restricted: false,
  monthly_contribution_amount: "5000.00",
  login_account_status: null,
} as unknown as Member;

const exitedMember = {
  ...ada,
  id: "member-2",
  membership_exit_date: "2026-09-30",
  membership_exit_reason: "Relocated",
  login_account_status: "active",
} as unknown as Member;

const conflictedMember = {
  ...ada,
  id: "member-3",
  name: "Abur Dooshima",
  conflicted: true,
} as unknown as Member;

function renderDetails(member: Member) {
  const handlers = {
    onClose: vi.fn(),
    onEdit: vi.fn(),
    onDelete: vi.fn(),
    onCreateLogin: vi.fn(),
    onDeactivateLogin: vi.fn(),
    onReactivateLogin: vi.fn(),
    onWithdraw: vi.fn(),
  };
  render(<MemberDetailsModal member={member} {...handlers} />);
  return handlers;
}

describe("MemberDetailsModal", () => {
  it("shows the rest of the record and every available action as a link", async () => {
    const handlers = renderDetails(ada);

    expect(screen.getByRole("dialog", { name: "Ada Obi" })).toBeInTheDocument();
    expect(screen.getByText("0001")).toBeInTheDocument();
    expect(screen.getByText("Registry")).toBeInTheDocument();
    expect(screen.getByText("ada@example.com")).toBeInTheDocument();
    expect(screen.getByText("₦5,000.00")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Edit member" }));
    expect(handlers.onEdit).toHaveBeenCalledWith(ada);

    expect(screen.getByRole("button", { name: "Delete member" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Create login" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Record exit" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Deactivate login" })).not.toBeInTheDocument();
  });

  it("offers the login action that matches the account's current state", () => {
    renderDetails(exitedMember);

    expect(screen.getByRole("button", { name: "Deactivate login" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Create login" })).not.toBeInTheDocument();
    // A recorded exit stands, so it can't be recorded again.
    expect(screen.queryByRole("button", { name: "Record exit" })).not.toBeInTheDocument();
    expect(screen.getByText("Relocated")).toBeInTheDocument();
  });

  it("keeps a conflicted member viewable but withholds every action", () => {
    renderDetails(conflictedMember);

    expect(screen.getByText("Abur Dooshima")).toBeInTheDocument();
    expect(screen.getByRole("note")).toHaveTextContent("another eligible officer");
    expect(screen.queryByRole("button", { name: "Edit member" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Delete member" })).not.toBeInTheDocument();
  });
});
