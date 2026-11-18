import StatusMessage from "@/components/ui/StatusMessage";
import LogoutControl from "@/components/ui/LogoutControl";
import PageSkeleton from "@/components/ui/PageSkeleton";
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
    return <PageSkeleton />;
  }

  return (
    <main className="page page--1000">
      <div className="page-header">
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
