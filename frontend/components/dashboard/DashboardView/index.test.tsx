import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { DashboardPageModel } from "../hooks/useDashboardPage";
import DashboardView from ".";

// The contribution card fetches its own data; this suite is about the header.
vi.mock("../ContributionCard", () => ({ default: () => null }));

function makeModel(overrides: Record<string, unknown> = {}): DashboardPageModel {
  return {
    auth: {
      user: {
        id: "user-1",
        username: "MCT-0001",
        role: "member",
        must_change_password: false,
        is_active: true,
        account_status: "active",
        is_super_admin: false,
        created_at: "2026-11-01T00:00:00Z",
      },
      logout: vi.fn(),
    },
    loading: false,
    member: {
      id: "member-1",
      psn: "MCT-0001",
      name: "Ada Obi",
      status: "financial",
      monthly_contribution_amount: "5000.00",
      loan_restricted: false,
    },
    settings: null,
    loansEnabled: false,
    feedback: { error: null, success: null },
    ...overrides,
  } as unknown as DashboardPageModel;
}

describe("DashboardView header", () => {
  it("welcomes the member in Last, First form with the name above log out", () => {
    render(<DashboardView model={makeModel()} />);

    expect(screen.getByRole("heading", { name: "Welcome, Obi, Ada" })).toBeInTheDocument();
    expect(screen.getByText("Obi, Ada")).toBeInTheDocument();
    expect(screen.getByText("PSN 0001")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Log out" })).toBeInTheDocument();
  });

  it("falls back to the plain heading until the member record loads", () => {
    render(<DashboardView model={makeModel({ member: null })} />);

    expect(screen.getByRole("heading", { name: "My Dashboard" })).toBeInTheDocument();
  });
});
