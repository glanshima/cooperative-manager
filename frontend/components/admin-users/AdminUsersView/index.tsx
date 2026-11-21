import StatusMessage from "@/components/ui/StatusMessage";
import type { AdminUsersPageModel } from "../hooks/useAdminUsersPage";
import CreateStaffForm from "../CreateStaffForm";
import StaffTable from "../StaffTable";

export default function AdminUsersView({ model }: { model: AdminUsersPageModel }) {
  return (
    <main className="page page--1000">
      <div className="page-header">
        <h1>Staff / Admin Users</h1>
        <div className="toolbar">
          <a href="/admin/offices">Offices</a>
          <a href="/admin/roles">Roles</a>
          <a href="/admin/audit">Audit log</a>
        </div>
      </div>

      {model.feedback.actionError && (
        <p style={{ color: "crimson", fontWeight: 600, display: "flex", alignItems: "center", gap: 8 }}>
          <span>{model.feedback.actionError}</span>
          <button onClick={model.feedback.dismissActionError} aria-label="Dismiss error" style={{ fontSize: 12 }}>
            Dismiss
          </button>
        </p>
      )}
      {model.feedback.success && <StatusMessage tone="success">{model.feedback.success}</StatusMessage>}
      {model.feedback.listError && (
        <StatusMessage tone="error">Unable to load staff accounts: {model.feedback.listError}</StatusMessage>
      )}

      <CreateStaffForm create={model.create} membersEnabled={model.membersEnabled} />
      <StaffTable table={model.table} membersEnabled={model.membersEnabled} />
    </main>
  );
}
