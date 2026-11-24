import Modal from "@/components/ui/Modal";

import type { DividendsPageModel } from "../hooks/useDividendsPage";
import { todayIso } from "../labels";

export default function DeclareModal({ model }: { model: DividendsPageModel }) {
  if (!model.declareForm.open || !model.detail) return null;

  return (
    <Modal
      title={`Declare the ${model.detail.run.fiscal_year} dividend`}
      onClose={() => model.declareForm.set({ open: false })}
      busy={model.busy}
      hint="Declaring recomputes the run against the current books, closes the fiscal year in the cashbook, and freezes the figures. It cannot be undone."
      maxWidth={520}
    >
      <form
        onSubmit={(e) => {
          e.preventDefault();
          void model.submitDeclare();
        }}
        style={{ display: "grid", gap: 12 }}
      >
        <label style={{ display: "block" }}>
          Declared on
          <input
            type="date"
            required
            max={todayIso()}
            min={model.detail.run.period_end}
            data-initial-focus
            aria-label="Declaration date"
            value={model.declareForm.on}
            onChange={(e) => model.declareForm.set({ on: e.target.value })}
            disabled={model.busy}
            style={{ display: "block", padding: 8, marginTop: 4 }}
          />
        </label>
        <div className="toolbar toolbar--end">
          <button
            type="button"
            disabled={model.busy}
            onClick={() => model.declareForm.set({ open: false })}
          >
            Cancel
          </button>
          <button type="submit" disabled={model.busy}>
            {model.busy ? "Declaring…" : "Declare dividend"}
          </button>
        </div>
      </form>
    </Modal>
  );
}
