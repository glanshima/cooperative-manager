import { render, renderHook, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { MouseEventHandler, ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { Settings } from "@/lib/api";
import { getSettings } from "@/lib/api";

import { useAdminNav } from "../hooks/useAdminNav";
import AdminNav from ".";

const { pathnameMock } = vi.hoisted(() => ({
  pathnameMock: vi.fn(() => "/admin/dashboard"),
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
};

const allModulesOff: Settings = {
  ...allModulesOn,
  members_module_enabled: false,
  loans_module_enabled: false,
  deductions_module_enabled: false,
};

const CORE_LABELS = [
  "Dashboard",
  "Staff / Admin users",
  "Offices",
  "Roles and permissions",
  "Audit log",
  "Settings",
];

beforeEach(() => {
  pathnameMock.mockReturnValue("/admin/dashboard");
  getSettingsMock.mockResolvedValue(allModulesOn);
});

describe("AdminNav", () => {
  it("offers a labelled navigation landmark with a link to every available area", async () => {
    render(<AdminNav />);

    const nav = screen.getByRole("navigation", { name: "Admin" });
    expect(await within(nav).findByRole("link", { name: "Members" })).toHaveAttribute(
      "href",
      "/members"
    );

    const expected: Array<[string, string]> = [
      ["Dashboard", "/admin/dashboard"],
      ["Members", "/members"],
      ["Loans", "/loans"],
      ["Loan applications", "/admin/loan-applications"],
      ["Disbursements", "/admin/disbursements"],
      ["Loan repayments", "/admin/loan-repayments"],
      ["Payroll deductions", "/admin/deductions"],
      ["Staff / Admin users", "/admin/users"],
      ["Offices", "/admin/offices"],
      ["Roles and permissions", "/admin/roles"],
      ["Audit log", "/admin/audit"],
      ["Settings", "/admin/settings"],
    ];
    for (const [label, href] of expected) {
      expect(within(nav).getByRole("link", { name: label })).toHaveAttribute("href", href);
    }
  });

  it("leaves out module areas that are switched off", async () => {
    getSettingsMock.mockResolvedValue(allModulesOff);
    render(<AdminNav />);

    const nav = screen.getByRole("navigation", { name: "Admin" });
    await waitFor(() =>
      expect(within(nav).queryByRole("link", { name: "Members" })).not.toBeInTheDocument()
    );
    expect(within(nav).queryByRole("link", { name: "Loans" })).not.toBeInTheDocument();
    expect(within(nav).queryByRole("link", { name: "Loan applications" })).not.toBeInTheDocument();
    expect(within(nav).queryByRole("link", { name: "Payroll deductions" })).not.toBeInTheDocument();

    for (const label of CORE_LABELS) {
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

  it("opens and closes the mobile menu from a labelled button", async () => {
    const user = userEvent.setup();
    render(<AdminNav />);

    const button = screen.getByRole("button", { name: "Open admin navigation" });
    const nav = screen.getByRole("navigation", { name: "Admin" });
    expect(button).toHaveAttribute("aria-expanded", "false");
    expect(button).toHaveAttribute("aria-controls", "admin-navigation");
    expect(nav).not.toHaveAttribute("data-open");

    await user.click(button);
    expect(screen.getByRole("button", { name: "Close admin navigation" })).toHaveAttribute(
      "aria-expanded",
      "true"
    );
    expect(nav).toHaveAttribute("data-open", "true");

    await user.click(screen.getByRole("button", { name: "Close admin navigation" }));
    expect(screen.getByRole("button", { name: "Open admin navigation" })).toHaveAttribute(
      "aria-expanded",
      "false"
    );
    expect(nav).not.toHaveAttribute("data-open");
  });

  it("closes the mobile menu on Escape and returns focus to the menu button", async () => {
    const user = userEvent.setup();
    render(<AdminNav />);

    await user.click(screen.getByRole("button", { name: "Open admin navigation" }));
    await user.keyboard("{Escape}");

    const button = screen.getByRole("button", { name: "Open admin navigation" });
    expect(button).toHaveAttribute("aria-expanded", "false");
    expect(button).toHaveFocus();
  });

  it("closes the mobile menu after following a link", async () => {
    const user = userEvent.setup();
    render(<AdminNav />);

    await user.click(screen.getByRole("button", { name: "Open admin navigation" }));
    await user.click(screen.getByRole("link", { name: "Audit log" }));

    expect(screen.getByRole("button", { name: "Open admin navigation" })).toHaveAttribute(
      "aria-expanded",
      "false"
    );
  });
});

describe("useAdminNav", () => {
  it("adds the module links once the enabled modules are known", async () => {
    const { result } = renderHook(() => useAdminNav());

    await waitFor(() =>
      expect(result.current.links.map((link) => link.label)).toEqual([
        "Dashboard",
        "Members",
        "Loans",
        "Loan applications",
        "Disbursements",
        "Loan repayments",
        "Payroll deductions",
        ...CORE_LABELS.slice(1),
      ])
    );
  });

  it("keeps only the core admin links when every module is off", async () => {
    getSettingsMock.mockResolvedValue(allModulesOff);
    const { result } = renderHook(() => useAdminNav());

    await waitFor(() =>
      expect(result.current.links.map((link) => link.label)).toEqual(CORE_LABELS)
    );
  });

  it("keeps only the core admin links when module settings cannot be loaded", async () => {
    getSettingsMock.mockRejectedValue(new Error("settings unavailable"));
    const { result } = renderHook(() => useAdminNav());

    await waitFor(() =>
      expect(result.current.links.map((link) => link.label)).toEqual(CORE_LABELS)
    );
  });
});
