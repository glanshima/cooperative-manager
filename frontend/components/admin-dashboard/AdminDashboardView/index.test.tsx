/**
 * Tests for AdminDashboardView rendering and useAdminDashboardPage
 * access guard / data-loading behaviour.
 *
 * AdminDashboardView tests: check that all expected nav links appear
 * when modules are enabled, and that module-gated links are hidden
 * when the corresponding module is disabled.
 *
 * useAdminDashboardPage tests: verify it calls getSettings (not any
 * member-scoped endpoint), and that it surfaces the loading/error states
 * correctly.
 */
import { render, screen, waitFor } from "@testing-library/react";
import { act, renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { CurrentUser, Settings } from "@/lib/api";
import { getSettings } from "@/lib/api";

import type { AdminDashboardPageModel } from "../hooks/useAdminDashboardPage";
import { useAdminDashboardPage } from "../hooks/useAdminDashboardPage";
import AdminDashboardView from ".";

// ---------------------------------------------------------------------------
// API mock — only getSettings should ever be called from the admin dashboard.
// ---------------------------------------------------------------------------
vi.mock("@/lib/api", () => ({
  getSettings: vi.fn(),
  // Stub every member-scoped function so any accidental call throws clearly.
  getMyMemberRecord: vi.fn().mockRejectedValue(
    new Error("getMyMemberRecord must NOT be called from the admin dashboard")
  ),
  listLoanApplications: vi.fn().mockRejectedValue(
    new Error("listLoanApplications must NOT be called from the admin dashboard (member endpoint)")
  ),
  listLoans: vi.fn().mockRejectedValue(
    new Error("listLoans must NOT be called from the admin dashboard (member endpoint)")
  ),
  listLoanTypes: vi.fn().mockRejectedValue(
    new Error("listLoanTypes must NOT be called from the admin dashboard")
  ),
}));

const getSettingsMock = vi.mocked(getSettings);

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------
const adminUser: CurrentUser = {
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

const allModulesOn: Settings = {
  id: "settings-1",
  loan_restriction_behavior: "block",
  loan_form_fee: "50.00",
  members_module_enabled: true,
  loans_module_enabled: true,
  deductions_module_enabled: true,
  cashbook_module_enabled: false,
  dividends_module_enabled: false,
};

const allModulesOff: Settings = {
  ...allModulesOn,
  members_module_enabled: false,
  loans_module_enabled: false,
  deductions_module_enabled: false,
};

function makeModel(overrides: Partial<AdminDashboardPageModel> = {}): AdminDashboardPageModel {
  return {
    auth: { user: adminUser, logout: vi.fn() },
    loading: false,
    settings: allModulesOn,
    settingsError: null,
    modules: {
      membersEnabled: true,
      loansEnabled: true,
      deductionsEnabled: true,
    },
    ...overrides,
  };
}

// ---------------------------------------------------------------------------
// AdminDashboardView rendering tests
// ---------------------------------------------------------------------------
describe("AdminDashboardView", () => {
  it("renders the heading and the signed-in username", () => {
    render(<AdminDashboardView model={makeModel()} />);

    expect(screen.getByRole("heading", { name: /admin dashboard/i })).toBeInTheDocument();
    expect(screen.getByText(/signed in as localadmin/i)).toBeInTheDocument();
  });

  it("shows all navigation links when every module is enabled", () => {
    render(<AdminDashboardView model={makeModel()} />);

    // Always-present admin links
    expect(screen.getByRole("link", { name: /staff \/ admin users/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /offices/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /roles and permissions/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /audit log/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /settings/i })).toBeInTheDocument();

    // Module-gated links (enabled)
    expect(screen.getByRole("link", { name: /member records/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /loan applications/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /disbursements/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /loan repayments/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /payroll deductions/i })).toBeInTheDocument();
  });

  it("hides module-gated links when every module is disabled", () => {
    render(
      <AdminDashboardView
        model={makeModel({
          settings: allModulesOff,
          modules: { membersEnabled: false, loansEnabled: false, deductionsEnabled: false },
        })}
      />
    );

    expect(screen.queryByRole("link", { name: /member records/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /loan applications/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /disbursements/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /loan repayments/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /payroll deductions/i })).not.toBeInTheDocument();

    // Core admin links always present
    expect(screen.getByRole("link", { name: /staff \/ admin users/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /audit log/i })).toBeInTheDocument();
  });

  it("renders each nav link with the correct href", () => {
    render(<AdminDashboardView model={makeModel()} />);

    expect(screen.getByRole("link", { name: /member records/i })).toHaveAttribute("href", "/members");
    expect(screen.getByRole("link", { name: /loan applications/i })).toHaveAttribute("href", "/admin/loan-applications");
    expect(screen.getByRole("link", { name: /disbursements/i })).toHaveAttribute("href", "/admin/disbursements");
    expect(screen.getByRole("link", { name: /loan repayments/i })).toHaveAttribute("href", "/admin/loan-repayments");
    expect(screen.getByRole("link", { name: /payroll deductions/i })).toHaveAttribute("href", "/admin/deductions");
    expect(screen.getByRole("link", { name: /staff \/ admin users/i })).toHaveAttribute("href", "/admin/users");
    expect(screen.getByRole("link", { name: /offices/i })).toHaveAttribute("href", "/admin/offices");
    expect(screen.getByRole("link", { name: /roles and permissions/i })).toHaveAttribute("href", "/admin/roles");
    expect(screen.getByRole("link", { name: /audit log/i })).toHaveAttribute("href", "/admin/audit");
    expect(screen.getByRole("link", { name: /settings/i })).toHaveAttribute("href", "/admin/settings");
  });

  it("shows the settings error banner when settings failed to load", () => {
    render(
      <AdminDashboardView
        model={makeModel({
          settings: null,
          settingsError: "Network error",
          modules: { membersEnabled: false, loansEnabled: false, deductionsEnabled: false },
        })}
      />
    );

    expect(screen.getByText(/unable to load module settings/i)).toBeInTheDocument();
    expect(screen.getByText(/network error/i)).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// useAdminDashboardPage hook tests (access guard / data-loading)
// ---------------------------------------------------------------------------
describe("useAdminDashboardPage", () => {
  const logout = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("does not fetch while auth is still loading", () => {
    getSettingsMock.mockResolvedValue(allModulesOn);

    renderHook(() => useAdminDashboardPage(true, null, logout));

    expect(getSettingsMock).not.toHaveBeenCalled();
  });

  it("does not fetch when user is null (unauthenticated)", () => {
    getSettingsMock.mockResolvedValue(allModulesOn);

    renderHook(() => useAdminDashboardPage(false, null, logout));

    expect(getSettingsMock).not.toHaveBeenCalled();
  });

  it("calls getSettings (and only getSettings) once auth resolves", async () => {
    getSettingsMock.mockResolvedValue(allModulesOn);

    const { result } = renderHook(() =>
      useAdminDashboardPage(false, adminUser, logout)
    );

    await waitFor(() => expect(result.current.loading).toBe(false));

    expect(getSettingsMock).toHaveBeenCalledTimes(1);
  });

  it("exposes correct module flags when all modules are on", async () => {
    getSettingsMock.mockResolvedValue(allModulesOn);

    const { result } = renderHook(() =>
      useAdminDashboardPage(false, adminUser, logout)
    );

    await waitFor(() => expect(result.current.loading).toBe(false));

    expect(result.current.modules.membersEnabled).toBe(true);
    expect(result.current.modules.loansEnabled).toBe(true);
    expect(result.current.modules.deductionsEnabled).toBe(true);
    expect(result.current.settingsError).toBeNull();
  });

  it("exposes correct module flags when all modules are off", async () => {
    getSettingsMock.mockResolvedValue(allModulesOff);

    const { result } = renderHook(() =>
      useAdminDashboardPage(false, adminUser, logout)
    );

    await waitFor(() => expect(result.current.loading).toBe(false));

    expect(result.current.modules.membersEnabled).toBe(false);
    expect(result.current.modules.loansEnabled).toBe(false);
    expect(result.current.modules.deductionsEnabled).toBe(false);
  });

  it("surfaces a settingsError and clears loading when getSettings rejects", async () => {
    getSettingsMock.mockRejectedValue(new Error("Service unavailable"));

    const { result } = renderHook(() =>
      useAdminDashboardPage(false, adminUser, logout)
    );

    await waitFor(() => expect(result.current.loading).toBe(false));

    expect(result.current.settingsError).toBe("Service unavailable");
    expect(result.current.settings).toBeNull();
  });

  it("re-fetches when auth transitions from loading to resolved", async () => {
    getSettingsMock.mockResolvedValue(allModulesOn);

    const { result, rerender } = renderHook(
      ({ authLoading, user }: { authLoading: boolean; user: CurrentUser | null }) =>
        useAdminDashboardPage(authLoading, user, logout),
      { initialProps: { authLoading: true, user: null as CurrentUser | null } }
    );

    // While still loading, nothing should be fetched.
    expect(getSettingsMock).not.toHaveBeenCalled();

    rerender({ authLoading: false, user: adminUser });

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(getSettingsMock).toHaveBeenCalledTimes(1);
  });
});
