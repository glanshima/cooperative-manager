import StatusMessage from "@/components/ui/StatusMessage";
import LogoutControl from "@/components/ui/LogoutControl";
import type { LoanRepaymentsPageModel } from "../hooks/useLoanRepaymentsPage";
import RepaymentReviewPanel from "../RepaymentReviewPanel";
import RepaymentsTable from "../RepaymentsTable";

export default function LoanRepaymentsView({
  model,
  identity,
}: {
  model: LoanRepaymentsPageModel;
  identity?: string | null;
}) {
  if (model.loading) {
    return <main style={{ padding: 32 }}>Loading...</main>;
  }

  return (
    <main style={{ padding: 32, maxWidth: 1000, margin: "0 auto" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <h1>Loan Repayments</h1>
        <LogoutControl identity={identity} onLogout={model.auth.logout} />
      </div>

      {model.feedback.error && (
        <StatusMessage tone="error">{model.feedback.error}</StatusMessage>
      )}

      <RepaymentsTable table={model.table} />
      <RepaymentReviewPanel review={model.review} />
    </main>
  );
}
