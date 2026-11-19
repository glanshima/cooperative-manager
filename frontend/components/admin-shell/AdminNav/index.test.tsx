import { render, renderHook, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { MouseEventHandler, ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { Settings } from "@/lib/api";
import { getSettings } from "@/lib/api";

import { useAdminNav } from "../hooks/useAdminNav";
import AdminNav from ".";

const { pathnameMock, logoutMock } = vi.hoisted(() => ({
  pathnameMock: vi.fn(() => "/admin/dashboard"),
  logoutMock: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  usePathname: pathnameMock,
}));

vi.mock("next/link", () => ({
  default: ({
    href,
    children,
    onClick,
    ...props
  }: {
    href: string;
    children: ReactNode;
    onClick?: MouseEventHandler<HTMLAnchorElement>;
  }) => (
    <a
      href={href}
      onClick={(event) => {
        event.preventDefault();
        onClick?.(event);
      }}
      {...props}
    >
      {children}
    </a>
  ),
}));

vi.mock("@/lib/api", () => ({
  getSettings: vi.fn(),
}));

vi.mock("@/lib/useAuth", () => ({
  useAuth: () => ({
    user: { username: "localadmin" },
    loading: false,
    logout: logoutMock,
  }),
}));

const getSettingsMock = vi.mocked(getSettings);

const allModulesOn: Settings = {
  id: "settings-1",
  loan_restriction_behavior: "block",
  loan_form_fee: "50.00",
  members_module_enabled: true,
  loans_module_enabled: true,
  deductions_module_enabled: true,
  cashbook_module_enabled: false,
  dividends_module_enabled: false,
  cooperative_name: "MACT Cooperative",
  cooperative_short_name: "MACT",
  cooperative_monogram: "M",
  logo_url: null,
};

const allModulesOff: Settings = {
  ...allModulesOn,
  members_module_enabled: false,
  loans_module_enabled: false,
  deductions_module_enabled: false,
};

const CORE_LABELS = ["Dashboard", "Settings", "Audit log"];

const LOAN_CHILDREN: Array<[string, string]> = [
  ["Loans", "/loans"],
  ["Loan applications", "/admin/loan-applications"],
  ["Disbursements", "/admin/disbursements"],
  ["Loan repayments", "/admin/loan-repayments"],
];

const SETTINGS_CHILDREN: Array<[string, string]> = [
  ["Staff / Admin users", "/admin/users"],
  ["Offices", "/admin/offices"],
  ["Roles and permissions", "/admin/roles"],
  ["Cooperative settings", "/admin/settings"],
];

beforeEach(() => {
  pathnameMock.mockReturnValue("/admin/dashboard");
  getSettingsMock.mockResolvedValue(allModulesOn);
});

describe("AdminNav", () => {
  it("offers a labelled navigation landmark with every top-level area", async () => {
    render(<AdminNav />);

    const nav = screen.getByRole("navigation", { name: "Admin" });
    expect(await within(nav).findByRole("link", { name: "Members" })).toHaveAttribute(
      "href",
      "/members"
    );

    expect(within(nav).getByRole("link", { name: "Dashboard" })).toHaveAttribute(
      "href",
      "/admin/dashboard"
    );
    expect(within(nav).getByRole("link", { name: "Payroll deductions" })).toHaveAttribute(
      "href",
      "/admin/deductions"
    );
    expect(within(nav).getByRole("link", { name: "Audit log" })).toHaveAttribute(
      "href",
      "/admin/audit"
    );
    expect(within(nav).getByRole("button", { name: "Loan Management" })).toBeInTheDocument();
    expect(within(nav).getByRole("button", { name: "Settings" })).toBeInTheDocument();
  });

  it("keeps the signed-in account above the platform credit", () => {
    render(<AdminNav />);

    const sidebar = screen.getByRole("complementary", { name: "Admin sidebar" });
    const identity = within(sidebar).getByText("localadmin");
    const logout = within(sidebar).getByRole("button", { name: "Log out" });
    const credit = within(sidebar).getByText("Powered by");
    expect(
      identity.compareDocumentPosition(logout) & Node.DOCUMENT_POSITION_FOLLOWING
    ).toBeTruthy();
    expect(
      logout.compareDocumentPosition(credit) & Node.DOCUMENT_POSITION_FOLLOWING
    ).toBeTruthy();
  });

  it("asks before logging out from the sidebar", async () => {
    const user = userEvent.setup();
    render(<AdminNav />);

    await user.click(screen.getByRole("button", { name: "Log out" }));
    const dialog = screen.getByRole("dialog", { name: "Log out?" });
    // Portalled to <body>, so the drawer's transform cannot size or clip it.
    expect(dialog.closest("aside")).toBeNull();
    expect(logoutMock).not.toHaveBeenCalled();

    await user.click(within(dialog).getByRole("button", { name: "Log out" }));
    expect(logoutMock).toHaveBeenCalledTimes(1);
  });

  it("shows the cooperative brand and the platform credit in the shell", () => {
    render(<AdminNav />);

    // The cooperative is named first in the top bar and the sidebar; the
    // platform credit stays secondary in the footer.
    expect(screen.getAllByText("MACT Cooperative").length).toBeGreaterThan(0);
    expect(screen.getByText("Powered by")).toBeInTheDocument();
    expect(screen.getByText("Koperra")).toBeInTheDocument();
  });

  it("keeps the loan and settings screens inside their menus", async () => {
    render(<AdminNav />);

    const nav = screen.getByRole("navigation", { name: "Admin" });
    await within(nav).findByRole("button", { name: "Loan Management" });

    for (const [label, href] of [...LOAN_CHILDREN, ...SETTINGS_CHILDREN]) {
      expect(within(nav).getByRole("link", { name: label })).toHaveAttribute("href", href);
    }
  });

  it("leaves out module areas that are switched off", async () => {
    getSettingsMock.mockResolvedValue(allModulesOff);
    render(<AdminNav />);

    const nav = screen.getByRole("navigation", { name: "Admin" });
    // Wait for the settings fetch to settle before checking what is missing.
    await within(nav).findByRole("button", { name: "Settings" });
    expect(within(nav).queryByRole("link", { name: "Members" })).not.toBeInTheDocument();
    expect(within(nav).queryByRole("link", { name: "Payroll deductions" })).not.toBeInTheDocument();
    expect(
      within(nav).queryByRole("button", { name: "Loan Management" })
    ).not.toBeInTheDocument();
    expect(within(nav).queryByRole("link", { name: "Loans" })).not.toBeInTheDocument();
    expect(
      within(nav).queryByRole("link", { name: "Loan applications" })
    ).not.toBeInTheDocument();

    // Core areas survive: top-level links stay and the settings menu stays.
    expect(within(nav).getByRole("link", { name: "Dashboard" })).toBeInTheDocument();
    expect(within(nav).getByRole("link", { name: "Audit log" })).toBeInTheDocument();
    expect(within(nav).getByRole("button", { name: "Settings" })).toBeInTheDocument();
    for (const [label] of SETTINGS_CHILDREN) {
      expect(within(nav).getByRole("link", { name: label })).toBeInTheDocument();
    }
  });

  it("marks the current page as the current link", async () => {
    pathnameMock.mockReturnValue("/admin/roles");
    render(<AdminNav />);

    expect(screen.getByRole("link", { name: "Roles and permissions" })).toHaveAttribute(
      "aria-current",
      "page"
    );
    expect(screen.getByRole("link", { name: "Dashboard" })).not.toHaveAttribute("aria-current");
  });

  it("opens the section containing the current page", async () => {
    pathnameMock.mockReturnValue("/admin/disbursements");
    render(<AdminNav />);

    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Loan Management" })).toHaveAttribute(
        "aria-expanded",
        "true"
      )
    );
    expect(screen.getByRole("button", { name: "Settings" })).toHaveAttribute(
      "aria-expanded",
      "false"
    );
  });

  it("opens a submenu from its labelled button", async () => {
    const user = userEvent.setup();
    render(<AdminNav />);

    const button = await screen.findByRole("button", { name: "Settings" });
    expect(button).toHaveAttribute("aria-expanded", "false");
    expect(button).toHaveAttribute("aria-controls", "admin-submenu-settings");

    await user.click(button);
    expect(button).toHaveAttribute("aria-expanded", "true");
  });

  it("toggles a submenu from the keyboard", async () => {
    const user = userEvent.setup();
    render(<AdminNav />);

    const button = await screen.findByRole("button", { name: "Settings" });
    button.focus();

    await user.keyboard("{Enter}");
    expect(button).toHaveAttribute("aria-expanded", "true");

    await user.keyboard("{Enter}");
    expect(button).toHaveAttribute("aria-expanded", "false");
  });

  it("closes an open submenu with Escape", async () => {
    const user = userEvent.setup();
    render(<AdminNav />);

    const button = await screen.findByRole("button", { name: "Loan Management" });
    await user.click(button);
    expect(button).toHaveAttribute("aria-expanded", "true");

    await user.keyboard("{Escape}");
    expect(button).toHaveAttribute("aria-expanded", "false");
  });

  it("closes one submenu when another opens", async () => {
    const user = userEvent.setup();
    render(<AdminNav />);

    const loans = await screen.findByRole("button", { name: "Loan Management" });
    const settings = screen.getByRole("button", { name: "Settings" });

    await user.click(loans);
    expect(loans).toHaveAttribute("aria-expanded", "true");

    await user.click(settings);
    expect(settings).toHaveAttribute("aria-expanded", "true");
    expect(loans).toHaveAttribute("aria-expanded", "false");
  });

  it("keeps the section containing the current page open after navigating within it", async () => {
    pathnameMock.mockReturnValue("/admin/settings");
    const first = render(<AdminNav />);

    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Settings" })).toHaveAttribute(
        "aria-expanded",
        "true"
      )
    );
    first.unmount();

    // A persistent sidebar shows where the officer is, so the section stays
    // expanded on the new page rather than collapsing after the click.
    pathnameMock.mockReturnValue("/admin/offices");
    render(<AdminNav />);

    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Settings" })).toHaveAttribute(
        "aria-expanded",
        "true"
      )
    );
    expect(screen.getByRole("link", { name: "Offices" })).toHaveAttribute(
      "aria-current",
      "page"
    );
  });

  it("leaves a section closed once the officer closes it", async () => {
    const user = userEvent.setup();
    render(<AdminNav />);

    const settings = await screen.findByRole("button", { name: "Settings" });
    await user.click(settings);
    await user.click(settings);

    expect(settings).toHaveAttribute("aria-expanded", "false");
    // Give the auto-open effect a chance to run again before asserting.
    await Promise.resolve();
    expect(settings).toHaveAttribute("aria-expanded", "false");
  });

  it("opens and closes the mobile drawer from a labelled button", async () => {
    const user = userEvent.setup();
    render(<AdminNav />);

    const button = screen.getByRole("button", { name: "Open admin navigation" });
    const sidebar = screen.getByRole("complementary", { name: "Admin sidebar" });
    expect(button).toHaveAttribute("aria-expanded", "false");
    expect(button).toHaveAttribute("aria-controls", "admin-sidebar");
    expect(sidebar).not.toHaveAttribute("data-open");

    await user.click(button);
    expect(screen.getByRole("button", { name: "Close admin navigation" })).toHaveAttribute(
      "aria-expanded",
      "true"
    );
    expect(sidebar).toHaveAttribute("data-open", "true");

    await user.click(screen.getByRole("button", { name: "Close admin navigation" }));
    expect(screen.getByRole("button", { name: "Open admin navigation" })).toHaveAttribute(
      "aria-expanded",
      "false"
    );
    expect(sidebar).not.toHaveAttribute("data-open");
  });

  it("closes the mobile drawer with its close button", async () => {
    const user = userEvent.setup();
    render(<AdminNav />);

    await user.click(screen.getByRole("button", { name: "Open admin navigation" }));
    await user.click(screen.getByRole("button", { name: "Close menu" }));

    expect(screen.getByRole("complementary", { name: "Admin sidebar" })).not.toHaveAttribute("data-open");
  });

  it("closes the mobile drawer on Escape and returns focus to the menu button", async () => {
    const user = userEvent.setup();
    render(<AdminNav />);

    await user.click(screen.getByRole("button", { name: "Open admin navigation" }));
    await user.keyboard("{Escape}");

    const button = screen.getByRole("button", { name: "Open admin navigation" });
    expect(button).toHaveAttribute("aria-expanded", "false");
    expect(button).toHaveFocus();
  });

  it("closes the mobile drawer after following a link", async () => {
    const user = userEvent.setup();
    render(<AdminNav />);

    await user.click(screen.getByRole("button", { name: "Open admin navigation" }));
    await user.click(screen.getByRole("link", { name: "Audit log" }));

    expect(screen.getByRole("button", { name: "Open admin navigation" })).toHaveAttribute(
      "aria-expanded",
      "false"
    );
  });

  it("closes the mobile drawer after following a submenu link", async () => {
    const user = userEvent.setup();
    render(<AdminNav />);

    await user.click(screen.getByRole("button", { name: "Open admin navigation" }));
    await user.click(screen.getByRole("button", { name: "Settings" }));
    await user.click(screen.getByRole("link", { name: "Cooperative settings" }));

    expect(screen.getByRole("button", { name: "Open admin navigation" })).toHaveAttribute(
      "aria-expanded",
      "false"
    );
  });
});

describe("useAdminNav", () => {
  it("groups the loan screens and settings screens under their own menus", async () => {
    const { result } = renderHook(() => useAdminNav());

    await waitFor(() =>
      expect(result.current.items.map((item) => item.label)).toEqual([
        "Dashboard",
        "Members",
        "Loan Management",
        "Payroll deductions",
        "Settings",
        "Audit log",
      ])
    );

    const loans = result.current.items.find((item) => item.label === "Loan Management");
    expect(loans?.kind === "group" && loans.children.map((child) => child.label)).toEqual([
      "Loans",
      "Loan applications",
      "Disbursements",
      "Loan repayments",
    ]);

    const settings = result.current.items.find((item) => item.label === "Settings");
    expect(settings?.kind === "group" && settings.children.map((child) => child.label)).toEqual([
      "Staff / Admin users",
      "Offices",
      "Roles and permissions",
      "Cooperative settings",
    ]);
  });

  it("keeps only the core admin areas when every module is off", async () => {
    getSettingsMock.mockResolvedValue(allModulesOff);
    const { result } = renderHook(() => useAdminNav());

    await waitFor(() =>
      expect(result.current.items.map((item) => item.label)).toEqual(CORE_LABELS)
    );
  });

  it("keeps only the core admin areas when module settings cannot be loaded", async () => {
    getSettingsMock.mockRejectedValue(new Error("settings unavailable"));
    const { result } = renderHook(() => useAdminNav());

    await waitFor(() =>
      expect(result.current.items.map((item) => item.label)).toEqual(CORE_LABELS)
    );
  });
});
