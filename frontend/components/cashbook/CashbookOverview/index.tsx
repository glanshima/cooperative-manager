import StatusMessage from "@/components/ui/StatusMessage";
import { formatMoney } from "@/components/deductions/labels";

import JournalLinesEditor from "../JournalLinesEditor";
import { emptyJournal } from "../journal";
import { todayIso } from "../labels";
import type { CashbookPageModel } from "../hooks/useCashbookPage";

export default function CashbookOverview({ model }: { model: CashbookPageModel }) {
  const { overview, opening, activeAccounts, permissions, busy } = model;

  if (!overview) return <p>Loading the books…</p>;

  return (
    <>
      <dl className="detail-grid">
        <div>
          <dt>Cash on hand</dt>
          <dd>₦{formatMoney(overview.cash_balance)}</dd>
        </div>
        <div>
          <dt>Bank</dt>
          <dd>₦{formatMoney(overview.bank_balance)}</dd>
        </div>
        <div>
          <dt>Accounts</dt>
          <dd>{overview.account_count}</dd>
        </div>
        <div>
          <dt>Journal entries</dt>
          <dd>{overview.entry_count}</dd>
        </div>
        <div>
          <dt>Opening balances</dt>
          <dd>{overview.opened ? `Posted ${overview.opening_date}` : "Not posted"}</dd>
        </div>
        <div>
          <dt>This month</dt>
          <dd>{overview.current_month_locked ? "Locked" : "Open"}</dd>
        </div>
      </dl>

      {!overview.opened && (
        <section aria-label="Opening balances" style={{ marginTop: 20 }}>
          <h2 style={{ margin: "0 0 6px", fontSize: 16 }}>Post the opening balances</h2>
          <p style={{ margin: "0 0 12px", color: "var(--text-muted)", fontSize: 14 }}>
            Bring the office&apos;s existing cash, bank, loans and member savings into the book.
            The opening journal must be the first entry and can be posted only once; from then on
            automatic postings start. Wrong amounts are corrected with a manual journal entry, not
            by editing this one.
          </p>

          {!permissions.canPost && (
            <StatusMessage tone="error">
              Posting needs the accounting.post permission. An officer with it must open the books.
            </StatusMessage>
          )}

          {permissions.canPost && !opening.open && (
            <p style={{ margin: 0 }}>
              <button type="button" className="link-button" onClick={() => opening.set({ ...opening, open: true })}>
                Enter opening balances
              </button>
            </p>
          )}

          {permissions.canPost && opening.open && (
            <div className="form-grid">
              <label style={{ fontSize: 13, color: "var(--text-muted)" }}>
                As of
                <input
                  type="date"
                  aria-label="Opening date"
                  value={opening.asOf}
                  max={todayIso()}
                  onChange={(e) => opening.set({ ...opening, asOf: e.target.value })}
                />
              </label>
              <input
                aria-label="Opening note"
                placeholder="Note (optional)"
                value={opening.note}
                onChange={(e) => opening.set({ ...opening, note: e.target.value })}
              />
              <div className="form-grid__full">
                <JournalLinesEditor
                  accounts={activeAccounts}
                  lines={opening.lines}
                  onChange={(lines) => opening.set({ ...opening, lines })}
                  disabled={busy}
                />
              </div>
              <div className="form-grid__full toolbar">
                <button type="button" disabled={busy} onClick={opening.submit}>
                  {busy ? "Posting…" : "Post opening balances"}
                </button>
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => opening.set({ ...opening, open: false, note: "", lines: emptyJournal() })}
                >
                  Cancel
                </button>
              </div>
            </div>
          )}
        </section>
      )}
    </>
  );
}
