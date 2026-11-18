import StatusMessage from "@/components/ui/StatusMessage";
import LogoutControl from "@/components/ui/LogoutControl";
import PageSkeleton from "@/components/ui/PageSkeleton";
import type { DisbursementsPageModel } from "../hooks/useDisbursementsPage";
import DisburseDialog from "../DisburseDialog";
import DisbursementFilters from "../DisbursementFilters";
import DisbursementsTable from "../DisbursementsTable";

export default function DisbursementsView({
  model,
  identity,
}: {
  model: DisbursementsPageModel;
  identity?: string | null;
}) {
  if (model.loading) {
    return <PageSkeleton />;
  }

  return (
    <main className="page page--1100">
      <div className="page-header">
        <h1>Disburse Loans</h1>
        <LogoutControl identity={identity} onLogout={model.auth.logout} />
      </div>
      <p style={{ color: "#555" }}>
        Approved loans awaiting disbursement. Disbursing sets the disbursement date to the 1st of
        this month, creates the active loan, and emails the member the full details.
      </p>

      {model.feedback.error && (
        <StatusMessage tone="error">{model.feedback.error}</StatusMessage>
      )}
      {model.feedback.success && (
        <StatusMessage tone="success">{model.feedback.success}</StatusMessage>
      )}

      <DisbursementFilters filters={model.filters} />
      <DisbursementsTable table={model.table} />
      <DisburseDialog dialog={model.dialog} />
    </main>
  );
}
