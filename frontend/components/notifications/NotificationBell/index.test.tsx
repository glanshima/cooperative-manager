import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { Notification, NotificationPage } from "@/lib/api";
import { getNotifications, markAllNotificationsRead, markNotificationRead } from "@/lib/api";

import NotificationBell from ".";

const { pushMock } = vi.hoisted(() => ({ pushMock: vi.fn() }));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: pushMock }),
}));

vi.mock("@/lib/api", () => ({
  getNotifications: vi.fn(),
  markNotificationRead: vi.fn(),
  markAllNotificationsRead: vi.fn(),
}));

const getNotificationsMock = vi.mocked(getNotifications);
const markReadMock = vi.mocked(markNotificationRead);
const markAllMock = vi.mocked(markAllNotificationsRead);

function note(overrides: Partial<Notification> = {}): Notification {
  return {
    id: "n1",
    category: "loan",
    title: "Loan application approved",
    body: "Your loan application was approved.",
    link_path: "/dashboard",
    is_read: false,
    read_at: null,
    created_at: "2026-11-19T10:00:00",
    ...overrides,
  };
}

function pageOf(items: Notification[]): NotificationPage {
  return {
    items,
    total: items.length,
    unread_count: items.filter((item) => !item.is_read).length,
  };
}

beforeEach(() => {
  pushMock.mockReset();
  markReadMock.mockReset();
  markAllMock.mockReset();
  getNotificationsMock.mockResolvedValue(pageOf([]));
});

describe("NotificationBell", () => {
  it("shows the unread count in the label and the badge", async () => {
    getNotificationsMock.mockResolvedValue(
      pageOf([note({ id: "n1" }), note({ id: "n2", title: "Repayment verified" })])
    );
    render(<NotificationBell />);

    const button = await screen.findByRole("button", { name: "Notifications, 2 unread" });
    expect(button).toHaveTextContent("2");
  });

  it("stays quiet when everything has been read", async () => {
    getNotificationsMock.mockResolvedValue(pageOf([note({ is_read: true, read_at: "x" })]));
    render(<NotificationBell />);

    const button = await screen.findByRole("button", { name: "Notifications" });
    await waitFor(() => expect(button).toHaveAttribute("aria-expanded", "false"));
    expect(button).not.toHaveTextContent(/^\d/);
  });

  it("opens a panel listing the notices, newest first", async () => {
    const user = userEvent.setup();
    getNotificationsMock.mockResolvedValue(
      pageOf([note({ id: "n1" }), note({ id: "n2", title: "Repayment verified" })])
    );
    render(<NotificationBell />);

    await user.click(await screen.findByRole("button", { name: /Notifications/ }));

    const dialog = screen.getByRole("dialog", { name: "Notifications" });
    expect(dialog).toHaveTextContent("Loan application approved");
    expect(dialog).toHaveTextContent("Repayment verified");
  });

  it("says so when there is nothing to show", async () => {
    const user = userEvent.setup();
    render(<NotificationBell />);

    await user.click(await screen.findByRole("button", { name: "Notifications" }));

    expect(
      within(screen.getByRole("dialog", { name: "Notifications" })).getByText(
        "No notifications yet."
      )
    ).toBeInTheDocument();
  });

  it("marks everything read and drops the badge", async () => {
    const user = userEvent.setup();
    getNotificationsMock.mockResolvedValue(pageOf([note({ id: "n1" }), note({ id: "n2" })]));
    render(<NotificationBell />);

    await user.click(await screen.findByRole("button", { name: "Notifications, 2 unread" }));
    await user.click(screen.getByRole("button", { name: "Mark all as read" }));

    expect(markAllMock).toHaveBeenCalledTimes(1);
    expect(await screen.findByRole("button", { name: "Notifications" })).toBeInTheDocument();
  });

  it("marks a notice read and follows its link when chosen", async () => {
    const user = userEvent.setup();
    getNotificationsMock.mockResolvedValue(pageOf([note()]));
    render(<NotificationBell />);

    await user.click(await screen.findByRole("button", { name: "Notifications, 1 unread" }));
    await user.click(screen.getByRole("button", { name: /Loan application approved/ }));

    expect(markReadMock).toHaveBeenCalledWith("n1");
    expect(pushMock).toHaveBeenCalledWith("/dashboard");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("closes on Escape and returns focus to the bell", async () => {
    const user = userEvent.setup();
    render(<NotificationBell />);

    const button = await screen.findByRole("button", { name: "Notifications" });
    await user.click(button);
    expect(screen.getByRole("dialog", { name: "Notifications" })).toBeInTheDocument();

    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(button).toHaveFocus();
  });

  it("closes when the click lands outside the panel", async () => {
    const user = userEvent.setup();
    render(<NotificationBell />);

    await user.click(await screen.findByRole("button", { name: "Notifications" }));
    expect(screen.getByRole("dialog", { name: "Notifications" })).toBeInTheDocument();

    await user.click(document.body);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
});
