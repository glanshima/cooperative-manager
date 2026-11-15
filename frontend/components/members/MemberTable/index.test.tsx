import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
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
    onOpenDetails: vi.fn(),
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
  it("lists each member by PSN and name with a way into their details", async () => {
    const handlers = renderTable([ada]);

    expect(screen.getByRole("columnheader", { name: "PSN" })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Name" })).toBeInTheDocument();
    expect(screen.getByText("0001")).toBeInTheDocument();
    expect(screen.getByText("Ada Obi")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Details" }));

    expect(handlers.onOpenDetails).toHaveBeenCalledWith(ada);
  });

  it("keeps a conflicted member on the list and labelled as such", () => {
    renderTable([ada, conflictedMember]);

    // Visible, and labelled -- hiding it broke search and totals.
    expect(screen.getByText("Abur Dooshima")).toBeInTheDocument();
    expect(screen.getByText("⚠ conflict")).toBeInTheDocument();

    // Details stays available so the officer can still read the record;
    // the modal withholds the actions that would change it.
    expect(screen.getAllByRole("button", { name: "Details" })).toHaveLength(2);
  });
});
