import StatusMessage from "@/components/ui/StatusMessage";
import LogoutControl from "@/components/ui/LogoutControl";
import type { LoanApplicationsPageModel } from "../hooks/useLoanApplicationsPage";
import ApplicationsTable from "../ApplicationsTable";
import ApplicationReviewPanel from "../ApplicationReviewPanel";

export default function LoanApplicationsView({
  model,
  identity,
}: {
  model: LoanApplicationsPageModel;
  identity?: string | null;
}) {
  if (model.loading) {
    return <main style={{ padding: 32 }}>Loading...</main>;
  }

  return (
    <main style={{ padding: 32, maxWidth: 1000, margin: "0 auto" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <h1>Loan Applications</h1>
        <LogoutControl identity={identity} onLogout={model.auth.logout} />
      </div>

      {model.feedback.error && (
        <StatusMessage tone="error">{model.feedback.error}</StatusMessage>
      )}

      <ApplicationsTable table={model.table} />
      <ApplicationReviewPanel review={model.review} />
    </main>
  );
}
