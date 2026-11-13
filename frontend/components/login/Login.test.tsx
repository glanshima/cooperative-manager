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
    
    expect(screen.getByRole("heading", { name: "MACT Cooperative Manager" })).toBeInTheDocument();
    expect(screen.getByPlaceholderText("PSN or username")).toBeInTheDocument();
    expect(screen.getByPlaceholderText("Password")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Log in" })).toBeInTheDocument();
  });
  
  it("shows login link when not signed in", () => {
    render(<LoginPage />);
    
    expect(screen.getByRole("link", { name: "Forgot your password?" })).toBeInTheDocument();
  });
});