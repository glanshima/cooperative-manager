import StatusMessage from "@/components/ui/StatusMessage";
import type { AuditPageModel } from "../hooks/useAuditPage";
import AuditDetailModal from "../AuditDetailModal";
import AuditFilters from "../AuditFilters";
import AuditTable from "../AuditTable";

export default function AuditView({ model }: { model: AuditPageModel }) {
  return (
    <main style={{ padding: 32, maxWidth: 1100, margin: "0 auto" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <h1>Audit Log</h1>
        <div style={{ display: "flex", gap: 12 }}>
          <a href="/admin/users">Users</a>
          <a href="/admin/offices">Offices</a>
          <a href="/admin/roles">Roles</a>
          <button onClick={model.auth.logout}>Log out</button>
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
