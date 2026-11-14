import StatusMessage from "@/components/ui/StatusMessage";
import LogoutControl from "@/components/ui/LogoutControl";
import type { AuditPageModel } from "../hooks/useAuditPage";
import AuditDetailModal from "../AuditDetailModal";
import AuditFilters from "../AuditFilters";
import AuditTable from "../AuditTable";

export default function AuditView({
  model,
  identity,
}: {
  model: AuditPageModel;
  identity?: string | null;
}) {
  return (
    <main className="page page--1100">
      <div className="page-header">
        <h1>Audit Log</h1>
        <div className="toolbar">
          <a href="/admin/users">Users</a>
          <a href="/admin/offices">Offices</a>
          <a href="/admin/roles">Roles</a>
          <LogoutControl identity={identity} onLogout={model.auth.logout} />
        </div>
      </div>
      <p style={{ color: "#555", fontSize: 14 }}>
        This is only reachable by staff accounts holding the <code>audit.view</code> permission -- ordinary
        members never see this page or its underlying API.
      </p>

      {model.feedback.error && (
        <StatusMessage tone="error">{model.feedback.error}</StatusMessage>
      )}

      <AuditFilters filters={model.filters} />
      <AuditTable table={model.table} />
      <AuditDetailModal detail={model.detail} />
    </main>
  );
}
