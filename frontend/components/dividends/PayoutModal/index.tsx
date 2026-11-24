import { formatMoney } from "@/components/deductions/labels";
import Modal from "@/components/ui/Modal";

import type { DividendsPageModel } from "../hooks/useDividendsPage";
import { PAYOUT_METHOD_LABELS, todayIso } from "../labels";

export default function PayoutModal({ model }: { model: DividendsPageModel }) {
  if (!model.payoutForm.open || !model.detail) return null;

  const { payoutForm, detail } = model;

  return (
    <Modal
      title={`Record a payout — ${detail.run.fiscal_year}`}
      onClose={() => payoutForm.set({ open: false })}
      busy={model.busy}
      hint="The batch clears the dividend payable and leaves the cash or bank account you choose. Allocations stay pending until a batch covers them."
      maxWidth={560}
    >
      <form
        onSubmit={(e) => {
          e.preventDefault();
          void model.submitPayout();
        }}
        style={{ display: "grid", gap: 12 }}
      >
        <fieldset style={{ border: "1px solid #ddd", borderRadius: 6, padding: 12 }}>
          <legend style={{ fontSize: 14 }}>Which allocations?</legend>
          <label style={{ display: "block", marginBottom: 6 }}>
            <input
              type="radio"
              name="payout-scope"
              checked={payoutForm.mode === "all"}
              onChange={() => payoutForm.set({ mode: "all" })}
              disabled={model.busy}
            />{" "}
            All pending — {detail.pending_allocations} allocations, ₦
            {formatMoney(model.pendingAmount)}
          </label>
          <label style={{ display: "block" }}>
            <input
              type="radio"
              name="payout-scope"
              checked={payoutForm.mode === "selected"}
              onChange={() => payoutForm.set({ mode: "selected" })}
              disabled={model.busy || model.selectedCount === 0}
            />{" "}
            Selected — {model.selectedCount} allocations, ₦{formatMoney(model.selectedAmount)}
          </label>
        </fieldset>

        <div className="form-grid">
          <label style={{ fontSize: 13, color: "var(--text-muted)" }}>
            Paid on
            <input
              type="date"
              max={todayIso()}
              min={detail.run.declared_on ?? undefined}
              data-initial-focus
              aria-label="Payout date"
              value={payoutForm.paidOn}
              onChange={(e) => payoutForm.set({ paidOn: e.target.value })}
              disabled={model.busy}
            />
          </label>
          <label style={{ fontSize: 13, color: "var(--text-muted)" }}>
            Paid from
            <select
              aria-label="Payout method"
              value={payoutForm.method}
              onChange={(e) =>
                payoutForm.set({ method: e.target.value as typeof payoutForm.method })
              }
              disabled={model.busy || model.payoutMethods.length === 1}
            >
              {model.payoutMethods.map((method) => (
                <option key={method} value={method}>
                  {PAYOUT_METHOD_LABELS[method]}
                </option>
              ))}
            </select>
          </label>
          <label className="form-grid__full" style={{ fontSize: 13, color: "var(--text-muted)" }}>
            Reference
            <input
              required
              maxLength={64}
              aria-label="Payment reference"
              value={payoutForm.reference}
              onChange={(e) => payoutForm.set({ reference: e.target.value })}
              disabled={model.busy}
            />
          </label>
          <label className="form-grid__full" style={{ fontSize: 13, color: "var(--text-muted)" }}>
            Note (optional)
            <input
              aria-label="Payout note"
              value={payoutForm.note}
              onChange={(e) => payoutForm.set({ note: e.target.value })}
              disabled={model.busy}
            />
          </label>
        </div>

        <div className="toolbar toolbar--end">
          <button
            type="button"
            disabled={model.busy}
            onClick={() => payoutForm.set({ open: false })}
          >
            Cancel
          </button>
          <button type="submit" disabled={model.busy}>
            {model.busy ? "Recording…" : "Record payout"}
          </button>
        </div>
      </form>
    </Modal>
  );
}
