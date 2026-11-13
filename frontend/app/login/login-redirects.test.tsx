/**
 * Tests for login redirect logic in LoginPage.
 *
 * The three branches from handleSubmit:
 *   1. must_change_password → /change-password
 *   2. role === "admin"    → /admin/dashboard
 *   3. role === "member"   → /dashboard
 *
 * We render LoginPage, mock the `login` API call, and assert that
 * router.push was called with the correct path.
 */
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { login } from "@/lib/api";

// next/navigation must be mocked before the component is imported.
const pushMock = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: pushMock, replace: vi.fn() }),
}));

vi.mock("@/lib/api", () => ({
  login: vi.fn(),
  // useAuth (via lib/useAuth) also imports from lib/api indirectly but
  // LoginPage does not use useAuth — it only calls login() — so we only
  // need to stub login here.
}));

const loginMock = vi.mocked(login);

// Import after mocks are set up.
// eslint-disable-next-line import/first
import LoginPage from "./page";

function fillAndSubmit() {
  return async () => {
    const user = userEvent.setup();
    render(<LoginPage />);
    await user.type(screen.getByPlaceholderText(/psn or username/i), "testuser");
    await user.type(screen.getByPlaceholderText(/password/i), "password123");
    await user.click(screen.getByRole("button", { name: /log in/i }));
  };
}

describe("LoginPage redirect behaviour", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("redirects to /change-password when must_change_password is true", async () => {
    loginMock.mockResolvedValue({
      access_token: "tok",
      token_type: "bearer",
      role: "admin",
      must_change_password: true,
    });

    await fillAndSubmit()();

    await waitFor(() => expect(pushMock).toHaveBeenCalledWith("/change-password"));
    expect(pushMock).not.toHaveBeenCalledWith("/admin/dashboard");
    expect(pushMock).not.toHaveBeenCalledWith("/dashboard");
  });

  it("redirects to /admin/dashboard for an admin who has already changed their password", async () => {
    loginMock.mockResolvedValue({
      access_token: "tok",
      token_type: "bearer",
      role: "admin",
      must_change_password: false,
    });

    await fillAndSubmit()();

    await waitFor(() => expect(pushMock).toHaveBeenCalledWith("/admin/dashboard"));
    expect(pushMock).not.toHaveBeenCalledWith("/change-password");
    expect(pushMock).not.toHaveBeenCalledWith("/dashboard");
  });

  it("redirects to /dashboard for a member who has already changed their password", async () => {
    loginMock.mockResolvedValue({
      access_token: "tok",
      token_type: "bearer",
      role: "member",
      must_change_password: false,
    });

    await fillAndSubmit()();

    await waitFor(() => expect(pushMock).toHaveBeenCalledWith("/dashboard"));
    expect(pushMock).not.toHaveBeenCalledWith("/change-password");
    expect(pushMock).not.toHaveBeenCalledWith("/admin/dashboard");
  });

  it("shows an error message and does not redirect when login fails", async () => {
    loginMock.mockRejectedValue(new Error("Invalid credentials"));

    await fillAndSubmit()();

    await waitFor(() =>
      expect(screen.getByText("Invalid credentials")).toBeInTheDocument()
    );
    expect(pushMock).not.toHaveBeenCalled();
  });
});
