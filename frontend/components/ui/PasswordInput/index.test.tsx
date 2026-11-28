import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import PasswordInput from "./index";

describe("PasswordInput", () => {
  it("hides the value by default and exposes a labelled toggle", () => {
    render(<PasswordInput label="Password" defaultValue="secret" autoComplete="current-password" />);

    const input = screen.getByLabelText("Password");
    const toggle = screen.getByRole("button", { name: "Show password" });

    expect(input).toHaveAttribute("type", "password");
    expect(input).toHaveAttribute("autocomplete", "current-password");
    expect(toggle).toHaveAttribute("type", "button");
    expect(toggle).toHaveAttribute("aria-pressed", "false");
    expect(toggle).toHaveAttribute("aria-controls", input.id);
  });

  it("shows and hides the value without changing it", async () => {
    const user = userEvent.setup();
    render(<PasswordInput label="Password" defaultValue="secret" />);

    const input = screen.getByLabelText("Password");
    await user.click(screen.getByRole("button", { name: "Show password" }));

    expect(input).toHaveAttribute("type", "text");
    expect(input).toHaveValue("secret");
    expect(screen.getByRole("button", { name: "Hide password" })).toHaveAttribute(
      "aria-pressed",
      "true"
    );

    await user.click(screen.getByRole("button", { name: "Hide password" }));

    expect(input).toHaveAttribute("type", "password");
    expect(input).toHaveValue("secret");
  });

  it("keeps each field's visibility independent", async () => {
    const user = userEvent.setup();
    render(
      <>
        <PasswordInput label="Current password" defaultValue="current" />
        <PasswordInput label="New password" defaultValue="new" />
      </>
    );

    await user.click(screen.getByRole("button", { name: "Show current password" }));

    expect(screen.getByLabelText("Current password")).toHaveAttribute("type", "text");
    expect(screen.getByLabelText("New password")).toHaveAttribute("type", "password");
  });

  it("works from the keyboard", async () => {
    const user = userEvent.setup();
    render(<PasswordInput label="Password" />);

    const toggle = screen.getByRole("button", { name: "Show password" });
    toggle.focus();
    await user.keyboard("{Enter}");

    expect(screen.getByLabelText("Password")).toHaveAttribute("type", "text");

    await user.keyboard(" ");

    expect(screen.getByLabelText("Password")).toHaveAttribute("type", "password");
  });

  it("never submits the surrounding form when toggled", async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn((event: React.FormEvent) => event.preventDefault());
    render(
      <form onSubmit={onSubmit}>
        <PasswordInput label="Password" />
        <button type="submit">Save</button>
      </form>
    );

    await user.click(screen.getByRole("button", { name: "Show password" }));

    expect(onSubmit).not.toHaveBeenCalled();
  });
});
