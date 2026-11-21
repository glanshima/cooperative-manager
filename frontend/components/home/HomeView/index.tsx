"use client";

import { useBranding } from "@/components/branding/BrandingProvider";
import LogoutControl from "@/components/ui/LogoutControl";
import { userDisplayName } from "@/lib/names";
import {
  DISBURSEMENT_PERMISSIONS,
  SETTINGS_PAGE_PERMISSIONS,
  hasAnyPermission,
  hasPermission,
} from "@/lib/permissions";
import type { HomePageModel } from "../hooks/useHomePage";

export default function HomeView({ model }: { model: HomePageModel }) {
  const { branding } = useBranding();
  const { user, loading, logout } = model.auth;
  const title = `${branding.cooperative_name} Manager`;

  if (loading) return <main className="page">Loading...</main>;

  if (!user) {
    return (
      <main className="page">
        <h1>{title}</h1>
        <p>
          <a href="/login">Log in &rarr;</a>
        </p>
      </main>
    );
  }

  const { membersEnabled, loansEnabled, deductionsEnabled } = model.modules;
  const permissions = user.permissions ?? [];
  const can = (code: string) => hasPermission(permissions, code);
  const canAny = (codes: readonly string[]) => hasAnyPermission(permissions, codes);

  return (
    <main className="page">
      <div className="page-header" style={{ maxWidth: 640 }}>
        <h1>{title}</h1>
        <LogoutControl identity={userDisplayName(user)} onLogout={logout} />
      </div>
      <p style={{ color: "#555" }}>Signed in as {user.username}.</p>

      {model.settingsError && (
        <p style={{ color: "crimson", fontWeight: 600 }}>
          Unable to load module settings: {model.settingsError}
        </p>
      )}

      {!model.settings && !model.settingsError && <p>Loading modules...</p>}

      {model.settings && (
        <ul>
          {user.role === "member" && (
            <li>
              <a href="/dashboard">Member Dashboard</a>
            </li>
          )}
          {membersEnabled && can("member.view") && (
            <li>
              <a href="/members">Members</a>
            </li>
          )}
          {loansEnabled && can("loan.view") && (
            <li>
              <a href="/loans">Loans</a>
            </li>
          )}
          {loansEnabled && user.role === "admin" && can("loan.view") && (
            <li>
              <a href="/admin/loan-applications">Loan Applications (admin review)</a>
            </li>
          )}
          {loansEnabled && user.role === "admin" && canAny(DISBURSEMENT_PERMISSIONS) && (
            <li>
              <a href="/admin/disbursements">Disbursements (admin)</a>
            </li>
          )}
          {loansEnabled && user.role === "admin" && can("repayment.view") && (
            <li>
              <a href="/admin/loan-repayments">Loan Repayments (admin review)</a>
            </li>
          )}
          {user.role === "admin" && deductionsEnabled && can("deduction.view") && (
            <li>
              <a href="/admin/deductions">Payroll Deductions (admin)</a>
            </li>
          )}
          {user.role === "admin" && can("admin.user_manage") && (
            <li>
              <a href="/admin/users">Staff / Admin Users</a>
            </li>
          )}
          {user.role === "admin" && can("admin.office_manage") && (
            <li>
              <a href="/admin/offices">Offices</a>
            </li>
          )}
          {user.role === "admin" && can("admin.role_manage") && (
            <li>
              <a href="/admin/roles">Roles</a>
            </li>
          )}
          {user.role === "admin" && can("audit.view") && (
            <li>
              <a href="/admin/audit">Audit log</a>
            </li>
          )}
          {user.role === "admin" && canAny(SETTINGS_PAGE_PERMISSIONS) && (
            <li>
              <a href="/admin/settings">Settings (admin)</a>
            </li>
          )}
        </ul>
      )}
    </main>
  );
}
