import Table from "@/components/ui/Table";

import type { CashbookPageModel } from "../hooks/useCashbookPage";

export default function LocksPanel({ model }: { model: CashbookPageModel }) {
  const { locks, lockForm, permissions, busy, overview } = model;

  return (
    <>
      <p style={{ color: "var(--text-muted)", fontSize: 14, marginTop: 0 }}>
        Locking a month is how the books freeze once they have been reconciled. While a month is
        locked, no manual entry, reversal or automatic posting can be dated inside it. Unlock only
        to correct a mistake, and lock again afterwards.
      </p>

      {overview && (
        <p style={{ fontSize: 13 }}>
          This month is <strong>{overview.current_month_locked ? "locked" : "open"}</strong>.
        </p>
      )}

      {permissions.canReconcile ? (
        <div className="form-grid" style={{ marginBottom: 16 }}>
          <label style={{ fontSize: 13, color: "var(--text-muted)" }}>
            Month
            <input
              type="month"
              aria-label="Month to lock"
              value={lockForm.month}
              onChange={(e) => lockForm.set({ ...lockForm, month: e.target.value })}
              disabled={busy}
            />
          </label>
          <input
            aria-label="Lock note"
            placeholder="Note (optional)"
            value={lockForm.note}
            onChange={(e) => lockForm.set({ ...lockForm, note: e.target.value })}
            disabled={busy}
          />
          <div className="form-grid__full toolbar">
            <button type="button" disabled={busy} onClick={model.lockMonth}>
              {busy ? "Locking…" : "Lock month"}
            </button>
          </div>
        </div>
      ) : (
        <p style={{ color: "var(--text-muted)", fontSize: 14 }}>
          Locking and unlocking needs the accounting.reconcile permission.
        </p>
      )}

      <Table>
        <thead>
          <tr>
            <th>Month</th>
            <th>Locked at</th>
            <th>Note</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          {locks.map((lock) => (
            <tr key={lock.period_start}>
              <td>{lock.period_start.slice(0, 7)}</td>
              <td>
                {lock.locked_at
                  ? new Date(lock.locked_at).toLocaleString(undefined, {
                      dateStyle: "medium",
                      timeStyle: "short",
                    })
                  : "—"}
              </td>
              <td>{lock.note || "—"}</td>
              <td>
                {permissions.canReconcile ? (
                  <button
                    type="button"
                    className="link-button"
                    disabled={busy}
                    onClick={() => model.unlockMonth(lock.period_start)}
                  >
                    Unlock
                  </button>
                ) : (
                  "—"
                )}
              </td>
            </tr>
          ))}
          {locks.length === 0 && (
            <tr>
              <td colSpan={4}>No month has been locked yet.</td>
            </tr>
          )}
        </tbody>
      </Table>
    </>
  );
}
