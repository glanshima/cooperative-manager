import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import LoginPage from "../../app/login/page";

// Mock the useRouter hook
vi.mock("next/navigation", () => ({
  useRouter: () => ({
    push: vi.fn(),
  }),
}));

// Mock the login API
vi.mock("../../lib/api", () => ({
  login: vi.fn(),
}));

describe("LoginPage", () => {
  it("renders login form", () => {
    render(<LoginPage />);

    expect(screen.getByRole("heading", { name: "Log in" })).toBeInTheDocument();
    expect(screen.getByPlaceholderText("PSN or username")).toBeInTheDocument();
    expect(screen.getByPlaceholderText("Password")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Log in" })).toBeInTheDocument();
  });

  it("shows login link when not signed in", () => {
    render(<LoginPage />);

    expect(screen.getByRole("link", { name: "Forgot your password?" })).toBeInTheDocument();
  });

  it("carries the cooperative identity and platform credit", () => {
    render(<LoginPage />);

    expect(screen.getByText("MACT Cooperative")).toBeInTheDocument();
    expect(screen.getByText("Koperra")).toBeInTheDocument();
  });
});
