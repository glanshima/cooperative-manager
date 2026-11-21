import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  getNotificationPreferences,
  updateNotificationPreferences,
} from "@/lib/api";

import NotificationPreferencesCard from ".";

vi.mock("@/lib/api", () => ({
  getNotificationPreferences: vi.fn(),
  updateNotificationPreferences: vi.fn(),
}));

const getPreferences = vi.mocked(getNotificationPreferences);
const updatePreferences = vi.mocked(updateNotificationPreferences);

describe("NotificationPreferencesCard", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders the saved switches", async () => {
    getPreferences.mockResolvedValue({ email_loan: false, email_repayment: true });

    render(<NotificationPreferencesCard />);

    const loan = await screen.findByRole("checkbox", {
      name: /loan applications, decisions and disbursements/i,
    });
    const repayment = screen.getByRole("checkbox", { name: /repayment confirmations/i });
    expect(loan).not.toBeChecked();
    expect(repayment).toBeChecked();
  });

  it("saves both switches", async () => {
    getPreferences.mockResolvedValue({ email_loan: true, email_repayment: true });
    updatePreferences.mockResolvedValue({ email_loan: true, email_repayment: false });
    const user = userEvent.setup();

    render(<NotificationPreferencesCard />);

    await user.click(await screen.findByRole("checkbox", { name: /repayment confirmations/i }));
    await user.click(screen.getByRole("button", { name: "Save preferences" }));

    await waitFor(() =>
      expect(updatePreferences).toHaveBeenCalledWith({ email_loan: true, email_repayment: false })
    );
    expect(await screen.findByText("Preferences saved.")).toBeInTheDocument();
    expect(updatePreferences.mock.calls.length).toBe(1);
  });

  it("shows a load failure instead of the switches", async () => {
    getPreferences.mockRejectedValue(new Error("Could not reach the server."));

    render(<NotificationPreferencesCard />);

    expect(await screen.findByText("Could not reach the server.")).toBeInTheDocument();
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
  });
});
