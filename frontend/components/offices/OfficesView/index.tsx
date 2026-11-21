import StatusMessage from "@/components/ui/StatusMessage";
import PageSkeleton from "@/components/ui/PageSkeleton";
import type { OfficesPageModel } from "../hooks/useOfficesPage";
import CreateOfficeForm from "../CreateOfficeForm";
import OfficesTable from "../OfficesTable";

export default function OfficesView({ model }: { model: OfficesPageModel }) {
  if (model.loading) {
    return <PageSkeleton />;
  }

  return (
    <main className="page page--700">
      <div className="page-header">
        <h1>Offices</h1>
        <div className="toolbar">
          <a href="/admin/users">Users</a>
          <a href="/admin/roles">Roles</a>
          <a href="/admin/audit">Audit log</a>
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
