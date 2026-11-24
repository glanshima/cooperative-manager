import Modal from "@/components/ui/Modal";

import type { DividendsPageModel } from "../hooks/useDividendsPage";

export default function NewRunModal({ model }: { model: DividendsPageModel }) {
  if (!model.newRun.open) return null;

  return (
    <Modal
      title="Prepare a dividend run"
      onClose={() => model.newRun.set({ open: false })}
      busy={model.busy}
      hint="The draft is computed from the books and the policy in Cooperative settings. Nothing is posted until it is declared."
      maxWidth={520}
    >
      <form
        onSubmit={(e) => {
          e.preventDefault();
          void model.submitNewRun();
        }}
        style={{ display: "grid", gap: 12 }}
      >
        <label style={{ display: "block" }}>
          Fiscal year
          <input
            type="number"
            min={2000}
            max={2100}
            required
            data-initial-focus
            aria-label="Fiscal year"
            value={model.newRun.fiscalYear}
            onChange={(e) => model.newRun.set({ fiscalYear: e.target.value })}
            disabled={model.busy}
            style={{ display: "block", padding: 8, marginTop: 4 }}
          />
        </label>
        <label style={{ display: "block" }}>
          Note (optional)
          <input
            aria-label="Run note"
            value={model.newRun.note}
            onChange={(e) => model.newRun.set({ note: e.target.value })}
            disabled={model.busy}
            style={{ display: "block", padding: 8, marginTop: 4 }}
          />
        </label>
        <div className="toolbar toolbar--end">
          <button
            type="button"
            disabled={model.busy}
            onClick={() => model.newRun.set({ open: false })}
          >
            Cancel
          </button>
          <button type="submit" disabled={model.busy}>
            {model.busy ? "Preparing…" : "Prepare draft"}
          </button>
        </div>
      </form>
    </Modal>
  );
}
