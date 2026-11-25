/**
 * The admin dashboard reads one aggregate endpoint whose sections are
 * already permission- and module-filtered by the backend. These tests pin
 * the two contract points: a null section renders nothing (it is never
 * shown as zero), and the period selector only exists when a figure on the
 * page actually depends on the period.
 */
import { render, screen, waitFor, within } from "@testing-library/react";
import { act, renderHook } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { AdminDashboard, CurrentUser } from "@/lib/api";
import { getAdminDashboard } from "@/lib/api";

import type { AdminDashboardPageModel } from "../hooks/useAdminDashboardPage";
import { useAdminDashboardPage } from "../hooks/useAdminDashboardPage";
import AdminDashboardView from ".";

vi.mock("@/lib/api", () => ({
  getAdminDashboard: vi.fn(),
}));

const getAdminDashboardMock = vi.mocked(getAdminDashboard);

const fullPermissions = [
  "member.view",
  "savings.view",
  "loan.view",
  "repayment.view",
  "deduction.view",
  "accounting.view",
  "dividend.view",
  "audit.view",
  "loan.review",
];

const adminUser: CurrentUser = {
  id: "user-1",
  username: "localadmin",
  role: "admin",
  member_id: null,
  must_change_password: false,
  is_active: true,
  account_status: "active",
  is_super_admin: false,
  permissions: fullPermissions,
  last_login_at: null,
  created_at: "2026-11-01T00:00:00Z",
};

const baseDashboard: AdminDashboard = {
  period: { key: "this_month", label: "This month", start: "2026-11-01", end: "2026-11-24" },
  members: { total: 120, financial: 100, non_financial: 20, exited: 3, joined: 4 },
  savings: { total: "50000.00", collected: "12000.00", paid_out: "500.00" },
  loans: {
    active_count: 8,
    outstanding: "12500.00",
    defaulted_count: 0,
    disbursed_count: 2,
    disbursed: "9000.00",
    repayments: { count: 5, amount: "2500.00" },
  },
  deductions: { confirmed_total: "8000.00", confirmed_members: 40, draft_count: 0, submitted_count: 0 },
  cashbook: { books_open: true, cash: "5000.00", bank: "25000.00", total: "30000.00" },
  dividends: {
    last_declared_year: 2025,
    last_declared_on: "2026-01-05",
    last_pool: "10000.00",
    unpaid_net: "1200.00",
    paid_net: "8800.00",
  },
  queues: [
    {
      key: "applications_review",
      label: "Loan applications awaiting review",
      count: 3,
      amount: null,
      href: "/admin/loan-applications",
    },
  ],
  activity: [
    {
      event_type: "loan.approve",
      action: "approve",
      actor: "jdoe",
      entity_type: "loan",
      entity_id: "loan-1",
      timestamp: "2026-11-24T10:00:00",
    },
  ],
  trend: {
    months: ["2026-06", "2026-07", "2026-08", "2026-09", "2026-10", "2026-11"],
    savings: ["1000.00", "2000.00", "1500.00", "0.00", "3000.00", "4000.00"],
    repayments: ["500.00", "0.00", "800.00", "600.00", "0.00", "900.00"],
  },
};

function makeDashboard(overrides: Partial<AdminDashboard> = {}): AdminDashboard {
  return { ...baseDashboard, ...overrides };
}

function makeModel(overrides: Partial<AdminDashboardPageModel> = {}): AdminDashboardPageModel {
  return {
    auth: { user: adminUser },
    period: "this_month",
    setPeriod: vi.fn(),
    data: makeDashboard(),
    error: null,
    loading: false,
    refreshing: false,
    reload: vi.fn(),
    dismissError: vi.fn(),
    ...overrides,
  };
}

describe("AdminDashboardView", () => {
  it("welcomes the admin by username", () => {
    render(<AdminDashboardView model={makeModel()} />);

    expect(screen.getByRole("heading", { name: "Welcome, localadmin" })).toBeInTheDocument();
  });

  it("greets the linked member's name instead of the login", () => {
    render(
      <AdminDashboardView
        model={makeModel({
          auth: { user: { ...adminUser, member_id: "member-1", member_name: "Ada Obi" } },
        })}
      />
    );

    expect(screen.getByRole("heading", { name: "Welcome, Obi, Ada" })).toBeInTheDocument();
  });

  it("shows the snapshot figures in their own card", () => {
    render(<AdminDashboardView model={makeModel()} />);

    expect(screen.getByText("₦50,000.00")).toBeInTheDocument();
    expect(screen.getByText("₦12,500.00")).toBeInTheDocument();
    expect(screen.getByText("₦30,000.00")).toBeInTheDocument();
    expect(screen.getByText("₦1,200.00")).toBeInTheDocument();
    expect(screen.getByText(/100 financial/)).toBeInTheDocument();
    expect(screen.getByText(/includes interest/)).toBeInTheDocument();
  });

  it("links cards only to screens the section belongs to", () => {
    render(<AdminDashboardView model={makeModel()} />);

    expect(screen.getByRole("link", { name: /^Members/ })).toHaveAttribute("href", "/members");
    expect(screen.getByRole("link", { name: /^Outstanding loans/ })).toHaveAttribute(
      "href",
      "/loans"
    );
    expect(screen.getByRole("link", { name: /^Cash & bank/ })).toHaveAttribute(
      "href",
      "/admin/cashbook"
    );
    expect(screen.getByRole("link", { name: /^Dividends unpaid/ })).toHaveAttribute(
      "href",
      "/admin/dividends"
    );
  });

  it("marks the cashbook as unavailable until its books are opened", () => {
    render(
      <AdminDashboardView
        model={makeModel({
          data: makeDashboard({
            cashbook: { books_open: false, cash: null, bank: null, total: null },
          }),
        })}
      />
    );

    expect(screen.getByText("Cashbook books not opened yet")).toBeInTheDocument();
    expect(screen.queryByText("₦30,000.00")).not.toBeInTheDocument();
  });

  it("renders nothing for sections the backend withheld", () => {
    render(
      <AdminDashboardView
        model={makeModel({
          data: makeDashboard({ members: null, trend: null, activity: null }),
        })}
      />
    );

    expect(screen.queryByText("Members")).not.toBeInTheDocument();
    expect(screen.queryByText("Last 6 months")).not.toBeInTheDocument();
    expect(screen.queryByText("Recent activity")).not.toBeInTheDocument();
  });

  it("lists pending work with a link to its queue", async () => {
    render(<AdminDashboardView model={makeModel()} />);

    const link = screen.getByRole("link", { name: /loan applications awaiting review/i });
    expect(link).toHaveAttribute("href", "/admin/loan-applications");
    expect(within(link).getByText("3")).toBeInTheDocument();
  });

  it("reassures an officer with no pending work, and hides the section from one who cannot act", () => {
    const { unmount } = render(
      <AdminDashboardView model={makeModel({ data: makeDashboard({ queues: [] }) })} />
    );
    expect(screen.getByText("Nothing is waiting on you right now.")).toBeInTheDocument();
    unmount();

    render(
      <AdminDashboardView
        model={makeModel({
          auth: { user: { ...adminUser, permissions: ["member.view"] } },
          data: makeDashboard({ queues: [] }),
        })}
      />
    );
    expect(screen.queryByText("Needs attention")).not.toBeInTheDocument();
  });

  it("switches the reporting period through the selector", async () => {
    const setPeriod = vi.fn();
    const user = userEvent.setup();
    render(<AdminDashboardView model={makeModel({ setPeriod })} />);

    const selector = screen.getByRole("group", { name: "Reporting period" });
    expect(within(selector).getByRole("button", { name: "This month" })).toHaveAttribute(
      "aria-pressed",
      "true"
    );

    await user.click(within(selector).getByRole("button", { name: "Last month" }));

    expect(setPeriod).toHaveBeenCalledWith("last_month");
  });

  it("hides the period selector when no figure on the page depends on it", () => {
    render(
      <AdminDashboardView
        model={makeModel({
          data: makeDashboard({
            members: null,
            savings: null,
            loans: null,
            deductions: null,
          }),
        })}
      />
    );

    expect(screen.queryByRole("group", { name: "Reporting period" })).not.toBeInTheDocument();
  });

  it("renders the six-month trend and recent activity", () => {
    render(<AdminDashboardView model={makeModel()} />);

    expect(
      screen.getByRole("img", {
        name: /monthly savings contributions and verified repayments over the last six months/i,
      })
    ).toBeInTheDocument();
    expect(screen.getByText("jdoe")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "View audit log" })).toHaveAttribute(
      "href",
      "/admin/audit"
    );
  });

  it("labels an empty trend window instead of drawing a flat chart", () => {
    render(
      <AdminDashboardView
        model={makeModel({
          data: makeDashboard({
            trend: {
              months: ["2026-06", "2026-07", "2026-08", "2026-09", "2026-10", "2026-11"],
              savings: ["0.00", "0.00", "0.00", "0.00", "0.00", "0.00"],
              repayments: null,
            },
          }),
        })}
      />
    );

    expect(
      screen.getByText(/no savings contributions or verified repayments/i)
    ).toBeInTheDocument();
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
  });

  it("offers retry when the first load fails, and keeps figures on a failed refresh", async () => {
    const reload = vi.fn();
    const user = userEvent.setup();
    const { unmount } = render(
      <AdminDashboardView model={makeModel({ data: null, error: "Service unavailable", reload })} />
    );

    expect(screen.getByText(/could not load the dashboard/i)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Try again" }));
    expect(reload).toHaveBeenCalledTimes(1);
    unmount();

    render(<AdminDashboardView model={makeModel({ error: "Service unavailable" })} />);
    expect(screen.getByText(/could not refresh the dashboard/i)).toBeInTheDocument();
    expect(screen.getByText(/previous load/i)).toBeInTheDocument();
    expect(screen.getByText("₦50,000.00")).toBeInTheDocument();
  });

  it("dismisses the error banner", async () => {
    const dismissError = vi.fn();
    const user = userEvent.setup();
    render(<AdminDashboardView model={makeModel({ error: "Service unavailable", dismissError })} />);

    await user.click(screen.getByRole("button", { name: "Dismiss error" }));

    expect(dismissError).toHaveBeenCalledTimes(1);
  });

  it("explains when the account has nothing to show", () => {
    render(
      <AdminDashboardView
        model={makeModel({
          auth: { user: { ...adminUser, permissions: [] } },
          data: makeDashboard({
            members: null,
            savings: null,
            loans: null,
            deductions: null,
            cashbook: null,
            dividends: null,
            queues: [],
            activity: null,
            trend: null,
          }),
        })}
      />
    );

    expect(screen.getByText(/no dashboard figures are available/i)).toBeInTheDocument();
  });
});

describe("useAdminDashboardPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("does not fetch while auth is still loading or the user is missing", () => {
    getAdminDashboardMock.mockResolvedValue(baseDashboard);

    renderHook(() => useAdminDashboardPage(true, null));
    renderHook(() => useAdminDashboardPage(false, null));

    expect(getAdminDashboardMock).not.toHaveBeenCalled();
  });

  it("loads the current month once auth resolves", async () => {
    getAdminDashboardMock.mockResolvedValue(baseDashboard);

    const { result } = renderHook(() => useAdminDashboardPage(false, adminUser));

    await waitFor(() => expect(result.current.loading).toBe(false));

    expect(getAdminDashboardMock).toHaveBeenCalledWith("this_month");
    expect(result.current.data?.members?.total).toBe(120);
    expect(result.current.error).toBeNull();
  });

  it("refetches with the newly selected period", async () => {
    getAdminDashboardMock.mockResolvedValue(baseDashboard);

    const { result } = renderHook(() => useAdminDashboardPage(false, adminUser));
    await waitFor(() => expect(result.current.loading).toBe(false));

    act(() => result.current.setPeriod("last_year"));

    await waitFor(() => expect(getAdminDashboardMock).toHaveBeenCalledWith("last_year"));
    expect(result.current.period).toBe("last_year");
  });

  it("surfaces a failed load and retries on demand", async () => {
    getAdminDashboardMock.mockRejectedValueOnce(new Error("Service unavailable"));
    const { result } = renderHook(() => useAdminDashboardPage(false, adminUser));

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.error).toBe("Service unavailable");
    expect(result.current.data).toBeNull();

    getAdminDashboardMock.mockResolvedValue(baseDashboard);
    act(() => result.current.reload());

    await waitFor(() => expect(result.current.data).not.toBeNull());
    expect(result.current.error).toBeNull();
  });

  it("clears a dismissed error without refetching", async () => {
    getAdminDashboardMock.mockRejectedValue(new Error("Service unavailable"));
    const { result } = renderHook(() => useAdminDashboardPage(false, adminUser));
    await waitFor(() => expect(result.current.error).toBe("Service unavailable"));

    act(() => result.current.dismissError());

    expect(result.current.error).toBeNull();
    expect(getAdminDashboardMock).toHaveBeenCalledTimes(1);
  });
});
