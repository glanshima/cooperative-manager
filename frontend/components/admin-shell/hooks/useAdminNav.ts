import { useEffect, useState } from "react";

import { getSettings, Settings } from "@/lib/api";
import { isModuleEnabled } from "@/lib/modules";

export interface AdminNavLink {
  href: string;
  label: string;
}

// Always available to an admin. Module-gated areas are added only once the
// server confirms the module is on, so the menu never advertises a page the
// application would refuse to open.
const CORE_ADMIN_LINKS: AdminNavLink[] = [
  { href: "/admin/users", label: "Staff / Admin users" },
  { href: "/admin/offices", label: "Offices" },
  { href: "/admin/roles", label: "Roles and permissions" },
  { href: "/admin/audit", label: "Audit log" },
  { href: "/admin/settings", label: "Settings" },
];

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

  const links: AdminNavLink[] = [{ href: "/admin/dashboard", label: "Dashboard" }];

  if (settings && isModuleEnabled(settings, "members")) {
    links.push({ href: "/members", label: "Members" });
  }
  if (settings && isModuleEnabled(settings, "loans")) {
    links.push(
      { href: "/loans", label: "Loans" },
      { href: "/admin/loan-applications", label: "Loan applications" },
      { href: "/admin/disbursements", label: "Disbursements" },
      { href: "/admin/loan-repayments", label: "Loan repayments" }
    );
  }
  if (settings && isModuleEnabled(settings, "deductions")) {
    links.push({ href: "/admin/deductions", label: "Payroll deductions" });
  }

  links.push(...CORE_ADMIN_LINKS);

  return { links };
}
