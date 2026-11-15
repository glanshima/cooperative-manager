import { useEffect, useState } from "react";

import { getSettings, Settings } from "@/lib/api";
import { isModuleEnabled } from "@/lib/modules";

export interface AdminNavLink {
  href: string;
  label: string;
}

export type AdminNavItem =
  | ({ kind: "link" } & AdminNavLink)
  | { kind: "group"; label: string; children: AdminNavLink[] };

// Always available to an admin. Module-gated areas are added only once the
// server confirms the module is on, so the menu never advertises a page the
// application would refuse to open.
export function useAdminNav() {
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

  const items: AdminNavItem[] = [{ kind: "link", href: "/admin/dashboard", label: "Dashboard" }];

  if (settings && isModuleEnabled(settings, "members")) {
    items.push({ kind: "link", href: "/members", label: "Members" });
  }
  if (settings && isModuleEnabled(settings, "loans")) {
    // Every stage of the loan workflow lives under one menu so related
    // screens stay together as more loan features are added.
    items.push({
      kind: "group",
      label: "Loan Management",
      children: [
        { href: "/loans", label: "Loans" },
        { href: "/admin/loan-applications", label: "Loan applications" },
        { href: "/admin/disbursements", label: "Disbursements" },
        { href: "/admin/loan-repayments", label: "Loan repayments" },
      ],
    });
  }
  if (settings && isModuleEnabled(settings, "deductions")) {
    items.push({ kind: "link", href: "/admin/deductions", label: "Payroll deductions" });
  }

  items.push(
    {
      kind: "group",
      label: "Settings",
      children: [
        { href: "/admin/users", label: "Staff / Admin users" },
        { href: "/admin/offices", label: "Offices" },
        { href: "/admin/roles", label: "Roles and permissions" },
        // The group carries the "Settings" name, so the page itself is
        // labelled for what it configures rather than repeating it.
        { href: "/admin/settings", label: "Cooperative settings" },
      ],
    },
    { kind: "link", href: "/admin/audit", label: "Audit log" }
  );

  return { items };
}
