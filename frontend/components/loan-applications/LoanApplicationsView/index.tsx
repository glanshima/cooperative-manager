import StatusMessage from "@/components/ui/StatusMessage";
import PageSkeleton from "@/components/ui/PageSkeleton";
import type { LoanApplicationsPageModel } from "../hooks/useLoanApplicationsPage";
import ApplicationsTable from "../ApplicationsTable";
import ApplicationReviewPanel from "../ApplicationReviewPanel";

export default function LoanApplicationsView({ model }: { model: LoanApplicationsPageModel }) {
  if (model.loading) {
    return <PageSkeleton />;
  }

  return (
    <main className="page page--1000">
      <div className="page-header">
        <h1>Loan Applications</h1>
      </div>

      {model.feedback.error && (
        <StatusMessage tone="error">{model.feedback.error}</StatusMessage>
      )}

      <ApplicationsTable table={model.table} />
      <ApplicationReviewPanel review={model.review} />
    </main>
  );
}
