import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { CurrentUser, Settings } from "@/lib/api";

import type { HomePageModel } from "../hooks/useHomePage";
import HomeView from ".";

const settings: Settings = {
  id: "settings-1",
  loan_restriction_behavior: "block",
  loan_form_fee: "50.00",
  members_module_enabled: true,
  loans_module_enabled: true,
  deductions_module_enabled: true,
  cashbook_module_enabled: true,
  dividends_module_enabled: true,
};

const admin: CurrentUser = {
  id: "user-1",
  username: "localadmin",
  role: "admin",
  member_id: null,
  must_change_password: false,
  is_active: true,
  account_status: "active",
  is_super_admin: true,
  last_login_at: null,
  created_at: "2026-11-01T00:00:00Z",
};

const member: CurrentUser = {
  ...admin,
  id: "user-2",
  username: "MCT-0001",
  role: "member",
  is_super_admin: false,
};

function makeModel({
  user = null,
  currentSettings = null,
  membersEnabled = false,
  loansEnabled = false,
  deductionsEnabled = false,
}: {
  user?: CurrentUser | null;
  currentSettings?: Settings | null;
  membersEnabled?: boolean;
  loansEnabled?: boolean;
  deductionsEnabled?: boolean;
}): HomePageModel {
  return {
    auth: { user, loading: false, logout: vi.fn() },
    settings: currentSettings,
    settingsError: null,
    modules: { membersEnabled, loansEnabled, deductionsEnabled },
  };
}

describe("HomeView", () => {
  it("shows only the login link when signed out", () => {
    render(<HomeView model={makeModel({})} />);

    expect(screen.getByRole("link", { name: /log in/i })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Members" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Settings (admin)" })).not.toBeInTheDocument();
  });

  it("shows admin pages but hides disabled modules", () => {
    render(
      <HomeView
        model={makeModel({
          user: admin,
          currentSettings: settings,
          membersEnabled: true,
          loansEnabled: false,
        })}
      />
    );

    expect(screen.getByRole("link", { name: "Members" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Staff / Admin Users" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Settings (admin)" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Loans" })).not.toBeInTheDocument();
    expect(
      screen.queryByRole("link", { name: "Loan Applications (admin review)" })
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("link", { name: "Payroll Deductions (admin)" })
    ).not.toBeInTheDocument();
  });

  it("shows the deductions link to admins while the module is enabled", () => {
    render(
      <HomeView
        model={makeModel({
          user: admin,
          currentSettings: settings,
          membersEnabled: true,
          loansEnabled: true,
          deductionsEnabled: true,
        })}
      />
    );

    expect(
      screen.getByRole("link", { name: "Payroll Deductions (admin)" })
    ).toBeInTheDocument();
  });

  it("shows a member only their dashboard and enabled modules", () => {
    render(
      <HomeView
        model={makeModel({
          user: member,
          currentSettings: settings,
          membersEnabled: false,
          loansEnabled: true,
        })}
      />
    );

    expect(screen.getByRole("link", { name: "Member Dashboard" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Loans" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Members" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Staff / Admin Users" })).not.toBeInTheDocument();
  });
});
