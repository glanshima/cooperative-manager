import StatusMessage from "@/components/ui/StatusMessage";
import type { OfficesPageModel } from "../hooks/useOfficesPage";
import CreateOfficeForm from "../CreateOfficeForm";
import OfficesTable from "../OfficesTable";

export default function OfficesView({ model }: { model: OfficesPageModel }) {
  if (model.loading) {
    return <main style={{ padding: 32 }}>Loading...</main>;
  }

  return (
    <main style={{ padding: 32, maxWidth: 700, margin: "0 auto" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <h1>Offices</h1>
        <div style={{ display: "flex", gap: 12 }}>
          <a href="/admin/users">Users</a>
          <a href="/admin/roles">Roles</a>
          <a href="/admin/audit">Audit log</a>
          <button onClick={model.auth.logout}>Log out</button>
        </div>
      </div>
      <p style={{ color: "#555", fontSize: 14 }}>
        Offices are a title/accountability grouping (President, Treasurer, ...). Add as many as your
        cooperative uses -- no code change is needed. Authorization itself comes from the Role you assign
        alongside an office, not the office name itself.
      </p>

      {model.feedback.error && (
        <StatusMessage tone="error">{model.feedback.error}</StatusMessage>
      )}

      <CreateOfficeForm form={model.form} />
      <OfficesTable table={model.table} />
    </main>
  );
}
