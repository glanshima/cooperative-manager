import { useEffect, useState } from "react";

import { getSettings, Settings } from "@/lib/api";
import { isModuleEnabled } from "@/lib/modules";
import {
  DISBURSEMENT_PERMISSIONS,
  SETTINGS_PAGE_PERMISSIONS,
  hasAnyPermission,
  hasPermission,
} from "@/lib/permissions";

export interface AdminNavLink {
  href: string;
  label: string;
}

export type AdminNavItem =
  | ({ kind: "link" } & AdminNavLink)
  | { kind: "group"; label: string; children: AdminNavLink[] };

// Every area is gated on a permission the server enforces, so the menu
// never offers a screen whose data calls would 403. Module-gated areas
// additionally wait for the server to confirm the module is on. The codes
// come from GET /api/auth/me, which resolves super admins to the full
// catalogue, so no role names are hard-coded here.
export function useAdminNav(permissions: string[]) {
  const [settings, setSettings] = useState<Settings | null>(null);

  useEffect(() => {
    let cancelled = false;
    getSettings()
      .then((data) => {
        if (!cancelled) setSettings(data);
      })
      .catch(() => {
        // The pages themselves surface settings errors; the menu simply
        // keeps module-gated links out until availability is known.
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const can = (code: string) => hasPermission(permissions, code);
  const canAny = (codes: readonly string[]) => hasAnyPermission(permissions, codes);

  const items: AdminNavItem[] = [{ kind: "link", href: "/admin/dashboard", label: "Dashboard" }];

  if (settings && isModuleEnabled(settings, "members") && can("member.view")) {
    items.push({ kind: "link", href: "/members", label: "Members" });
  }

  const loanChildren: AdminNavLink[] = [];
  if (can("loan.view")) {
    loanChildren.push(
      { href: "/loans", label: "Loans" },
      { href: "/admin/loan-applications", label: "Loan applications" }
    );
  }
  if (canAny(DISBURSEMENT_PERMISSIONS)) {
    loanChildren.push({ href: "/admin/disbursements", label: "Disbursements" });
  }
  if (can("repayment.view")) {
    loanChildren.push({ href: "/admin/loan-repayments", label: "Loan repayments" });
  }
  if (settings && isModuleEnabled(settings, "loans") && loanChildren.length > 0) {
    // Every stage of the loan workflow lives under one menu so related
    // screens stay together as more loan features are added.
    items.push({ kind: "group", label: "Loan Management", children: loanChildren });
  }

  if (settings && isModuleEnabled(settings, "deductions") && can("deduction.view")) {
    items.push({ kind: "link", href: "/admin/deductions", label: "Payroll deductions" });
  }

  const settingsChildren: AdminNavLink[] = [];
  if (can("admin.user_manage")) {
    settingsChildren.push({ href: "/admin/users", label: "Staff / Admin users" });
  }
  if (can("admin.office_manage")) {
    settingsChildren.push({ href: "/admin/offices", label: "Offices" });
  }
  if (can("admin.role_manage")) {
    settingsChildren.push({ href: "/admin/roles", label: "Roles and permissions" });
  }
  if (canAny(SETTINGS_PAGE_PERMISSIONS)) {
    // The group carries the "Settings" name, so the page itself is
    // labelled for what it configures rather than repeating it.
    settingsChildren.push({ href: "/admin/settings", label: "Cooperative settings" });
  }
  if (settingsChildren.length > 0) {
    items.push({ kind: "group", label: "Settings", children: settingsChildren });
  }

  if (can("audit.view")) {
    items.push({ kind: "link", href: "/admin/audit", label: "Audit log" });
  }

  return { items };
}
