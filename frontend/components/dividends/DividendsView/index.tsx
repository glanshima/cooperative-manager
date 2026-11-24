import ConfirmDialog from "@/components/ui/ConfirmDialog";
import StatusMessage from "@/components/ui/StatusMessage";

import DeclareModal from "../DeclareModal";
import ManifestModal from "../ManifestModal";
import NewRunModal from "../NewRunModal";
import PayoutModal from "../PayoutModal";
import RunDetail from "../RunDetail";
import RunList from "../RunList";
import type { DividendsPageModel } from "../hooks/useDividendsPage";

export default function DividendsView({ model }: { model: DividendsPageModel }) {
  return (
    <main className="page page--1200">
      <div className="page-header">
        <h1>Dividends</h1>
        <p style={{ margin: "4px 0 0", color: "var(--text-muted)", fontSize: 14 }}>
          Share out a fiscal year&apos;s surplus: close the year, set aside the reserve and
          honorarium, and pay each eligible member their share.
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

      {model.loading ? (
        <p>Loading dividend runs…</p>
      ) : (
        <>
          {model.selectedId ? <RunDetail model={model} /> : <RunList model={model} />}

          <NewRunModal model={model} />
          <DeclareModal model={model} />
          <PayoutModal model={model} />
          <ManifestModal model={model} />

          {model.deleteTarget && (
            <ConfirmDialog
              title="Delete this draft?"
              message={`The draft dividend run for ${model.deleteTarget.fiscal_year} will be removed. Nothing has been posted, so no figures are affected.`}
              confirmLabel="Delete draft"
              busy={model.busy}
              onConfirm={model.confirmDelete}
              onCancel={() => model.setDeleteTarget(null)}
            />
          )}
        </>
      )}
    </main>
  );
}
