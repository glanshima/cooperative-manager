import StatusMessage from "@/components/ui/StatusMessage";
import type { AdminDashboardPageModel } from "../hooks/useAdminDashboardPage";

interface NavCardProps {
  href: string;
  label: string;
  description: string;
}

function NavCard({ href, label, description }: NavCardProps) {
  return (
    <a
      href={href}
      style={{
        display: "block",
        padding: "16px 20px",
        border: "1px solid #ddd",
        borderRadius: 6,
        textDecoration: "none",
        color: "inherit",
        background: "#fafafa",
      }}
    >
      <strong style={{ display: "block", marginBottom: 4, color: "#111" }}>{label}</strong>
      <span style={{ fontSize: 13, color: "#666" }}>{description}</span>
    </a>
  );
}

export default function AdminDashboardView({ model }: { model: AdminDashboardPageModel }) {
  const { user, logout } = model.auth;
  const { membersEnabled, loansEnabled, deductionsEnabled } = model.modules;

  return (
    <main style={{ padding: 32, maxWidth: 900, margin: "0 auto" }}>
      <div
        style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}
      >
        <h1>Admin Dashboard</h1>
        <button onClick={logout}>Log out</button>
      </div>

      {user && (
        <p style={{ color: "#555", marginBottom: 24 }}>Signed in as {user.username}.</p>
      )}

      {model.settingsError && (
        <StatusMessage tone="error">
          Unable to load module settings: {model.settingsError}
        </StatusMessage>
      )}

      {/* Member management */}
      {membersEnabled && (
        <section style={{ marginBottom: 32 }}>
          <h2 style={{ fontSize: 15, fontWeight: 600, color: "#444", marginBottom: 12 }}>
            Members
          </h2>
          <div style={{ display: "grid", gap: 10, gridTemplateColumns: "repeat(auto-fill, minmax(260px, 1fr))" }}>
            <NavCard
              href="/members"
              label="Member records"
              description="View, search, and manage cooperative members."
            />
          </div>
        </section>
      )}

      {/* Loan workflow */}
      {loansEnabled && (
        <section style={{ marginBottom: 32 }}>
          <h2 style={{ fontSize: 15, fontWeight: 600, color: "#444", marginBottom: 12 }}>
            Loans
          </h2>
          <div style={{ display: "grid", gap: 10, gridTemplateColumns: "repeat(auto-fill, minmax(260px, 1fr))" }}>
            <NavCard
              href="/admin/loan-applications"
              label="Loan applications"
              description="Review, verify fees, and approve or reject applications."
            />
            <NavCard
              href="/admin/disbursements"
              label="Disbursements"
              description="Prepare, approve, and reconcile loan disbursements."
            />
            <NavCard
              href="/admin/loan-repayments"
              label="Loan repayments"
              description="Verify member-submitted repayments."
            />
          </div>
        </section>
      )}

      {/* Payroll deductions */}
      {deductionsEnabled && (
        <section style={{ marginBottom: 32 }}>
          <h2 style={{ fontSize: 15, fontWeight: 600, color: "#444", marginBottom: 12 }}>
            Deductions
          </h2>
          <div style={{ display: "grid", gap: 10, gridTemplateColumns: "repeat(auto-fill, minmax(260px, 1fr))" }}>
            <NavCard
              href="/admin/deductions"
              label="Payroll deductions"
              description="Create, submit, and confirm monthly payroll deduction schedules."
            />
          </div>
        </section>
      )}

      {/* Administration */}
      <section style={{ marginBottom: 32 }}>
        <h2 style={{ fontSize: 15, fontWeight: 600, color: "#444", marginBottom: 12 }}>
          Administration
        </h2>
        <div style={{ display: "grid", gap: 10, gridTemplateColumns: "repeat(auto-fill, minmax(260px, 1fr))" }}>
          <NavCard
            href="/admin/users"
            label="Staff / Admin users"
            description="Create and manage admin accounts, roles, and assignments."
          />
          <NavCard
            href="/admin/offices"
            label="Offices"
            description="Create and manage offices and positions."
          />
          <NavCard
            href="/admin/roles"
            label="Roles and permissions"
            description="Define roles and configure which permissions they grant."
          />
          <NavCard
            href="/admin/audit"
            label="Audit log"
            description="Browse the full record of system events and changes."
          />
          <NavCard
            href="/admin/settings"
            label="Settings"
            description="Configure cooperative-wide settings and module toggles."
          />
        </div>
      </section>
    </main>
  );
}
