import { act, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import DashboardHeader from "./index";

function renderHeader(overrides: Partial<Parameters<typeof DashboardHeader>[0]> = {}) {
  const onLogout = vi.fn();
  render(
    <DashboardHeader
      name="Obi, Ada"
      fallbackTitle="My Dashboard"
      username="MCT-0001"
      onLogout={onLogout}
      {...overrides}
    />
  );
  return { onLogout };
}

describe("DashboardHeader", () => {
  it("welcomes by name with the username above the log out control", () => {
    renderHeader();

    expect(screen.getByRole("heading", { name: "Welcome, Obi, Ada" })).toBeInTheDocument();
    const username = screen.getByText("MCT-0001");
    const button = screen.getByRole("button", { name: "Log out" });
    expect(
      username.compareDocumentPosition(button) & Node.DOCUMENT_POSITION_FOLLOWING
    ).toBeTruthy();
  });

  it("still welcomes before the five-second mark", () => {
    vi.useFakeTimers();
    try {
      renderHeader();
      act(() => {
        vi.advanceTimersByTime(4_999);
      });
      expect(screen.getByRole("heading", { name: "Welcome, Obi, Ada" })).toBeInTheDocument();
    } finally {
      vi.useRealTimers();
    }
  });

  it("moves to a time-of-day greeting after five seconds", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date(2026, 10, 14, 14, 0));
    try {
      renderHeader();
      act(() => {
        vi.advanceTimersByTime(5_000);
      });
      expect(
        screen.getByRole("heading", { name: "Good afternoon, Obi, Ada" })
      ).toBeInTheDocument();
    } finally {
      vi.useRealTimers();
    }
  });

  it("keeps the plain heading when there is no name to greet", () => {
    renderHeader({ name: null, username: null });

    expect(screen.getByRole("heading", { name: "My Dashboard" })).toBeInTheDocument();
    expect(screen.queryByText("MCT-0001")).not.toBeInTheDocument();
  });

  it("asks before logging out and cancelling keeps the session", async () => {
    const user = userEvent.setup();
    const { onLogout } = renderHeader();

    await user.click(screen.getByRole("button", { name: "Log out" }));
    const dialog = screen.getByRole("dialog", { name: "Log out?" });
    expect(onLogout).not.toHaveBeenCalled();

    await user.click(within(dialog).getByRole("button", { name: "Cancel" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(onLogout).not.toHaveBeenCalled();
  });

  it("logs out only after the confirmation is accepted", async () => {
    const user = userEvent.setup();
    const { onLogout } = renderHeader();

    await user.click(screen.getByRole("button", { name: "Log out" }));
    const dialog = screen.getByRole("dialog", { name: "Log out?" });
    await user.click(within(dialog).getByRole("button", { name: "Log out" }));

    expect(onLogout).toHaveBeenCalledTimes(1);
  });

  it("closes the confirmation on Escape without logging out", async () => {
    const user = userEvent.setup();
    const { onLogout } = renderHeader();

    await user.click(screen.getByRole("button", { name: "Log out" }));
    expect(screen.getByRole("dialog", { name: "Log out?" })).toBeInTheDocument();

    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(onLogout).not.toHaveBeenCalled();
  });
});
