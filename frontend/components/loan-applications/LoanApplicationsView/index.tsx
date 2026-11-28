import FilterNotice from "@/components/ui/FilterNotice";
import StatusMessage from "@/components/ui/StatusMessage";
import PageSkeleton from "@/components/ui/PageSkeleton";
import type { LoanApplicationsPageModel } from "../hooks/useLoanApplicationsPage";
import ApplicationsTable from "../ApplicationsTable";
import ApplicationReviewPanel from "../ApplicationReviewPanel";

const FILTER_LABELS = {
  review: "Showing applications awaiting review.",
  payment: "Showing application fees awaiting verification.",
} as const;

const VIEWS = [
  { key: "pending", label: "Pending" },
  { key: "approved", label: "Approved / awaiting disbursement" },
  { key: "rejected", label: "Rejected" },
  { key: "cancelled", label: "Cancelled" },
  { key: "all", label: "All" },
] as const;

export default function LoanApplicationsView({ model }: { model: LoanApplicationsPageModel }) {
  if (model.loading) {
    return <PageSkeleton />;
  }

  return (
    <main className="page page--1000">
      <div className="page-header">
        <h1>Loan Applications</h1>
      </div>

      {(model.filter.current === "review" || model.filter.current === "payment") && (
        <FilterNotice onClear={model.filter.clear}>
          {FILTER_LABELS[model.filter.current]}
        </FilterNotice>
      )}

      <div className="toolbar" style={{ marginBottom: 16 }}>
        <div role="group" aria-label="Application views" style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
          {VIEWS.map((view) => (
            <button
              key={view.key}
              type="button"
              aria-pressed={model.filter.current === view.key}
              onClick={() => model.filter.set(view.key)}
              style={{ fontWeight: model.filter.current === view.key ? 700 : 400 }}
            >
              {view.label}
            </button>
          ))}
        </div>
      </div>

      {model.feedback.error && (
        <StatusMessage tone="error">{model.feedback.error}</StatusMessage>
      )}

      <ApplicationsTable table={model.table} />
      <ApplicationReviewPanel review={model.review} />
    </main>
  );
}
