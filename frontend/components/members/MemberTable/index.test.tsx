import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { Member } from "@/lib/api";

import MemberTable from "./index";

const ada = {
  id: "member-1",
  psn: "MCT-0001",
  name: "Ada Obi",
  department: "Registry",
  status: "financial",
  loan_restricted: false,
  phone: "08000000001",
  login_account_status: null,
} as unknown as Member;

const conflictedMember = {
  ...ada,
  id: "member-2",
  psn: "MCT-0002",
  name: "Abur Dooshima",
  conflicted: true,
} as unknown as Member;

function renderTable(members: Member[]) {
  const handlers = {
    onPageChange: vi.fn(),
    onEdit: vi.fn(),
    onDelete: vi.fn(),
    onCreateLogin: vi.fn(),
    onDeactivateLogin: vi.fn(),
    onReactivateLogin: vi.fn(),
    onWithdraw: vi.fn(),
  };
  render(
    <MemberTable
      members={members}
      loading={false}
      listError={null}
      skip={0}
      total={members.length}
      limit={25}
      {...handlers}
    />
  );
  return handlers;
}

describe("MemberTable", () => {
  it("renders the usual actions for an ordinary member", () => {
    renderTable([ada]);
    expect(screen.getByRole("button", { name: "Edit" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Delete" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Create login" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Record exit" })).toBeInTheDocument();
  });

  it("keeps a conflicted member on the list but offers no way to change them", () => {
    const handlers = renderTable([ada, conflictedMember]);

    // Visible, and labelled as such -- hiding it broke search and totals.
    expect(screen.getByText("Abur Dooshima")).toBeInTheDocument();
    expect(screen.getByText("⚠ conflict")).toBeInTheDocument();

    // Every action belongs to the unconflicted row only.
    expect(screen.getAllByRole("button", { name: "Edit" })).toHaveLength(1);
    expect(screen.getAllByRole("button", { name: "Record exit" })).toHaveLength(1);
    expect(screen.getByText("Another officer must handle this member")).toBeInTheDocument();
    expect(handlers.onEdit).not.toHaveBeenCalled();
  });
});
