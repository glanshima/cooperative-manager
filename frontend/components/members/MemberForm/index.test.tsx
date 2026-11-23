import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
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
    isOpen: true,
    busy: false,
    contributionLocked: false,
    policy: { minimumContribution: 0, standardContribution: 0 },
    setField: vi.fn(),
    submit: vi.fn(),
    openCreate: vi.fn(),
    close: vi.fn(),
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

describe("MemberForm modal", () => {
  it("renders as a labelled dialog for both create and edit", () => {
    const { rerender } = render(<MemberForm form={makeForm()} />);

    expect(screen.getByRole("dialog")).toHaveAccessibleName("Add member");
    expect(screen.getByRole("button", { name: "Close member form" })).toBeInTheDocument();
    expect(screen.getByText(/Closing this form discards/)).toBeInTheDocument();

    rerender(<MemberForm form={makeForm({ editingId: "member-1" })} />);
    expect(screen.getByRole("dialog")).toHaveAccessibleName("Edit member");
  });

  it("closes from the close button and Escape", async () => {
    const user = userEvent.setup();
    const form = makeForm();
    render(<MemberForm form={form} />);

    await user.click(screen.getByRole("button", { name: "Close member form" }));
    expect(form.close).toHaveBeenCalledTimes(1);

    await user.keyboard("{Escape}");
    expect(form.close).toHaveBeenCalledTimes(2);
  });

  it("locks the dialog while a save is in flight", async () => {
    const user = userEvent.setup();
    const form = makeForm({ busy: true });
    render(<MemberForm form={form} />);

    expect(screen.getByRole("button", { name: "Close member form" })).toBeDisabled();
    await user.keyboard("{Escape}");
    expect(form.close).not.toHaveBeenCalled();
  });
});
