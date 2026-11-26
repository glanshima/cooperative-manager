import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { DashboardPageModel } from "../hooks/useDashboardPage";
import DashboardView from ".";

// The contribution card fetches its own data; this suite is about the header.
vi.mock("../ContributionCard", () => ({ default: () => null }));
// Same for the email preference card.
vi.mock("../NotificationPreferences", () => ({ default: () => null }));
// The bell polls its own endpoint and has its own suite.
vi.mock("@/components/notifications/NotificationBell", () => ({ default: () => null }));

// The shell asks the media query which chrome to show, so jsdom needs
// matchMedia. Desktop is the default.
function stubMatchMedia(matches: boolean) {
  vi.stubGlobal("matchMedia", (query: string) => ({
    matches,
    media: query,
    onchange: null,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    addListener: vi.fn(),
    removeListener: vi.fn(),
    dispatchEvent: vi.fn(),
  }));
}

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
        permissions: [],
        created_at: "2026-11-01T00:00:00Z",
      },
      logout: vi.fn(),
    },
    loading: false,
    member: {
      id: "member-1",
      psn: "MCT-0001",
      name: "Obi, Ada Ngozi",
      status: "financial",
      monthly_contribution_amount: "5000.00",
      loan_restricted: false,
    },
    settings: null,
    loansEnabled: false,
    deductionsEnabled: false,
    summary: {
      savings: null,
      deductions: null,
      loanBalance: null,
      notifications: null,
      activity: [],
    },
    feedback: { error: null, success: null },
    ...overrides,
  } as unknown as DashboardPageModel;
}

beforeEach(() => {
  stubMatchMedia(false);
});

describe("DashboardView header", () => {
  it("abbreviates other names in the greeting but prints the full name above log out", () => {
    render(<DashboardView model={makeModel()} />);

    expect(screen.getByRole("heading", { name: "Welcome, Obi, Ada N." })).toBeInTheDocument();
    expect(screen.getByText("Obi, Ada Ngozi")).toBeInTheDocument();
    expect(screen.getByText("PSN 0001")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Log out" })).toBeInTheDocument();
    expect(screen.getByText("MACT Cooperative")).toBeInTheDocument();
    expect(screen.getByText("Koperra")).toBeInTheDocument();
  });

  it("falls back to the plain heading until the member record loads", () => {
    render(<DashboardView model={makeModel({ member: null })} />);

    expect(screen.getByRole("heading", { name: "My Dashboard" })).toBeInTheDocument();
  });
});

describe("DashboardView summary", () => {
  it("shows the server's savings, loan and deduction figures", () => {
    render(
      <DashboardView
        model={makeModel({
          loansEnabled: true,
          deductionsEnabled: true,
          applications: { items: [] },
          loans: { items: [] },
          apply: { showForm: false, toggle: vi.fn() },
          summary: {
            savings: { member_id: "member-1", savings_balance: "16000.00", months_contributed: 3 },
            loanBalance: {
              member_id: "member-1",
              active_loan_count: 1,
              total_outstanding_balance: "2700.00",
              conflicted: false,
            },
            deductions: {
              month: "2026-11-01",
              status: "confirmed",
              contribution: "5000.00",
              loan_repayment: "0.00",
              other: "0.00",
              total: "5000.00",
            },
            notifications: null,
            activity: [],
          },
        })}
      />
    );

    // The savings figure appears in the stat card and again in the overview.
    expect(screen.getAllByText("₦16,000.00").length).toBeGreaterThan(0);
    expect(screen.getByText("Across 3 confirmed months")).toBeInTheDocument();
    expect(screen.getByText("1 active loan")).toBeInTheDocument();
    expect(screen.getByText("Confirmed")).toBeInTheDocument();
    expect(screen.getByText(/November 2026/)).toBeInTheDocument();
  });

  it("says a disabled module is disabled instead of showing zero", () => {
    render(<DashboardView model={makeModel()} />);

    expect(screen.getByText("Loans are disabled")).toBeInTheDocument();
    expect(screen.getByText("Deductions are disabled")).toBeInTheDocument();
  });
});
