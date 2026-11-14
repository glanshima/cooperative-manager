import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { MembersPageModel } from "../hooks/useMembersPage";
import MemberForm from ".";

function makeForm(overrides: Record<string, unknown> = {}) {
  return {
    values: {
      psn: "",
      first_name: "",
      last_name: "",
      other_names: "",
      status: "financial",
      loan_restricted: false,
    },
    editingId: null,
    contributionLocked: false,
    setField: vi.fn(),
    submit: vi.fn(),
    reset: vi.fn(),
    startEdit: vi.fn(),
    nok: {
      isMember: null,
      selected: null,
      query: "",
      results: [],
      chooseIsMember: vi.fn(),
      setQuery: vi.fn(),
      search: vi.fn(),
      select: vi.fn(),
      clearSelected: vi.fn(),
    },
    ...overrides,
  } as unknown as MembersPageModel["form"];
}

describe("MemberForm registration fields", () => {
  it("captures the name in three fields, in printed order", () => {
    render(<MemberForm form={makeForm()} />);

    const fields = screen.getAllByRole("textbox").map((el) => el.getAttribute("aria-label"));
    const nameFields = fields.filter((label) =>
      ["Last name", "First name", "Other name(s)"].includes(label ?? "")
    );
    expect(nameFields).toEqual(["Last name", "First name", "Other name(s)"]);
  });

  it("marks the required inputs with an asterisk", () => {
    render(<MemberForm form={makeForm()} />);

    expect(screen.getByLabelText("PSN")).toBeRequired();
    expect(screen.getByLabelText("Last name")).toBeRequired();
    expect(screen.getByLabelText("First name")).toBeRequired();
    expect(screen.getByLabelText("Other name(s)")).not.toBeRequired();
    expect(screen.getByPlaceholderText("PSN *")).toBeInTheDocument();
    expect(screen.getByPlaceholderText("Last name *")).toBeInTheDocument();
    expect(screen.getByPlaceholderText("First name *")).toBeInTheDocument();
    expect(screen.getByText("Next of kin *")).toBeInTheDocument();
  });

  it("does not mark the next-of-kin question when editing an existing member", () => {
    render(<MemberForm form={makeForm({ editingId: "member-1" })} />);

    expect(screen.getByText("Next of kin")).toBeInTheDocument();
    expect(screen.queryByText("Next of kin *")).not.toBeInTheDocument();
  });
});
