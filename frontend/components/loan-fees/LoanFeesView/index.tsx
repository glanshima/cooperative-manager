import PageSkeleton from "@/components/ui/PageSkeleton";
import StatusMessage from "@/components/ui/StatusMessage";
import type { LoanFeesPageModel } from "../hooks/useLoanFeesPage";
import FeePaymentsTable from "../FeePaymentsTable";
import FeeReviewPanel from "../FeeReviewPanel";

export default function LoanFeesView({ model }: { model: LoanFeesPageModel }) {
  if (model.loading && model.table.items.length === 0) {
    return <PageSkeleton />;
  }

  return (
    <main className="page page--1000">
      <div className="page-header">
        <h1>Loan fees</h1>
      </div>

      {model.feedback.error && (
        <StatusMessage tone="error" onDismiss={model.feedback.dismissError}>
          {model.feedback.error}
        </StatusMessage>
      )}
      {model.feedback.success && (
        <StatusMessage tone="success" onDismiss={model.feedback.dismissSuccess}>
          {model.feedback.success}
        </StatusMessage>
      )}

      <p style={{ color: "#555", marginTop: 0 }}>
        Loan fees are paid separately from the loan. Verified payments here are the
        cooperative's income record; they never alter a loan's payout or balance. Application
        fees are verified in Loan Applications and are not requested again here.
      </p>

      <div style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 16 }}>
        <label>
          Show:{" "}
          <select
            value={model.scope}
            onChange={(e) => model.setScope(e.target.value as LoanFeesPageModel["scope"])}
          >
            <option value="queue">Awaiting verification</option>
            <option value="all">All fee payments</option>
          </select>
        </label>
        <span style={{ fontSize: 13, color: "#666" }}>{model.total} payment(s)</span>
      </div>

      <FeePaymentsTable table={model.table} />
      <FeeReviewPanel review={model.review} />
    </main>
  );
}
