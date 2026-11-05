import StatusMessage from "@/components/ui/StatusMessage";
import type { LoanApplicationsPageModel } from "../hooks/useLoanApplicationsPage";
import ApplicationsTable from "../ApplicationsTable";
import ApplicationReviewPanel from "../ApplicationReviewPanel";

export default function LoanApplicationsView({
  model,
}: {
  model: LoanApplicationsPageModel;
}) {
  if (model.loading) {
    return <main style={{ padding: 32 }}>Loading...</main>;
  }

  return (
    <main style={{ padding: 32, maxWidth: 1000, margin: "0 auto" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <h1>Loan Applications</h1>
        <button onClick={model.auth.logout}>Log out</button>
      </div>

      {model.feedback.error && (
        <StatusMessage tone="error">{model.feedback.error}</StatusMessage>
      )}

      <ApplicationsTable table={model.table} />
      <ApplicationReviewPanel review={model.review} />
    </main>
  );
}
