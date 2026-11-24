import StatusMessage from "@/components/ui/StatusMessage";

import AccountsPanel from "../AccountsPanel";
import CashbookOverview from "../CashbookOverview";
import JournalPanel from "../JournalPanel";
import LocksPanel from "../LocksPanel";
import ReportsPanel from "../ReportsPanel";
import type { CashbookPageModel, CashbookTab } from "../hooks/useCashbookPage";

const TABS: { key: CashbookTab; label: string }[] = [
  { key: "overview", label: "Overview" },
  { key: "journal", label: "Journal" },
  { key: "accounts", label: "Chart of accounts" },
  { key: "reports", label: "Reports" },
  { key: "locks", label: "Period locks" },
];

export default function CashbookView({ model }: { model: CashbookPageModel }) {
  return (
    <main className="page page--1200">
      <div className="page-header">
        <h1>Cashbook</h1>
        <p style={{ margin: "4px 0 0", color: "var(--text-muted)", fontSize: 14 }}>
          Double-entry books: every movement debits one account and credits another. Savings,
          loans, fees and payroll deductions post here automatically.
        </p>
      </div>

      {model.feedback.error && (
        <StatusMessage tone="error" onDismiss={model.feedback.dismissError} dismissLabel="Dismiss error">
          {model.feedback.error}
        </StatusMessage>
      )}
      {model.feedback.success && (
        <StatusMessage
          tone="success"
          onDismiss={model.feedback.dismissSuccess}
          dismissLabel="Dismiss message"
        >
          {model.feedback.success}
        </StatusMessage>
      )}

      <div
        role="tablist"
        aria-label="Cashbook view"
        style={{ display: "flex", gap: 8, marginBottom: 16, flexWrap: "wrap" }}
      >
        {TABS.map((tab) => (
          <button
            key={tab.key}
            role="tab"
            aria-selected={model.tab === tab.key}
            onClick={() => model.setTab(tab.key)}
            style={{ fontWeight: model.tab === tab.key ? 700 : 400 }}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {model.loading ? (
        <p>Loading the books…</p>
      ) : (
        <>
          {model.tab === "overview" && <CashbookOverview model={model} />}
          {model.tab === "journal" && <JournalPanel model={model} />}
          {model.tab === "accounts" && <AccountsPanel model={model} />}
          {model.tab === "reports" && <ReportsPanel model={model} />}
          {model.tab === "locks" && <LocksPanel model={model} />}
        </>
      )}
    </main>
  );
}
