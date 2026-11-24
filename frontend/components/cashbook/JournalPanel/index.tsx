import { useState } from "react";

import { formatMoney } from "@/components/deductions/labels";
import Pagination from "@/components/ui/Pagination";
import Table from "@/components/ui/Table";
import type { CashbookEntry } from "@/lib/api";

import JournalLinesEditor from "../JournalLinesEditor";
import { emptyJournal } from "../journal";
import { monthLabel, SOURCE_LABELS, todayIso } from "../labels";
import type { CashbookPageModel } from "../hooks/useCashbookPage";

export default function JournalPanel({ model }: { model: CashbookPageModel }) {
  const { entries, accounts, overview, filters, permissions, entry, reversal, busy, locks } = model;
  const [search, setSearch] = useState(filters.value.q);

  const lockedMonths = new Set(locks.map((lock) => lock.period_start.slice(0, 7)));
  const entryMonth = entry.entryDate.slice(0, 7);
  const entryLocked = entry.open && lockedMonths.has(entryMonth);

  const reversedIds = new Set(
    (entries?.items ?? [])
      .map((item) => item.reverses_entry_id)
      .filter((value): value is string => Boolean(value))
  );

  const totalDebit = (entries?.items ?? []).reduce(
    (sum, item) => sum + item.lines.reduce((lineSum, line) => lineSum + Number(line.debit), 0),
    0
  );

  return (
    <>
      <div className="toolbar" style={{ marginBottom: 12 }}>
        <label style={{ fontSize: 13, color: "var(--text-muted)" }}>
          From
          <input
            type="date"
            aria-label="Entries from"
            value={filters.value.start}
            onChange={(e) => filters.change({ start: e.target.value })}
          />
        </label>
        <label style={{ fontSize: 13, color: "var(--text-muted)" }}>
          To
          <input
            type="date"
            aria-label="Entries to"
            value={filters.value.end}
            onChange={(e) => filters.change({ end: e.target.value })}
          />
        </label>
        <select
          aria-label="Entry source"
          value={filters.value.source}
          onChange={(e) =>
            filters.change({ source: e.target.value as CashbookPageModel["filters"]["value"]["source"] })
          }
        >
          <option value="">All sources</option>
          {Object.entries(SOURCE_LABELS).map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </select>
        <select
          aria-label="Account filter"
          value={filters.value.accountId}
          onChange={(e) => filters.change({ accountId: e.target.value })}
        >
          <option value="">All accounts</option>
          {accounts.map((account) => (
            <option key={account.id} value={account.id}>
              {account.code} — {account.name}
            </option>
          ))}
        </select>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            filters.change({ q: search });
          }}
          style={{ display: "flex", gap: 6 }}
        >
          <input
            aria-label="Search narration or reference"
            placeholder="Search narration or reference"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
          <button type="submit">Search</button>
        </form>
        {(filters.value.start ||
          filters.value.end ||
          filters.value.source ||
          filters.value.accountId ||
          filters.value.q) && (
          <button
            type="button"
            onClick={() => {
              setSearch("");
              filters.reset();
            }}
          >
            Clear filters
          </button>
        )}

        {overview?.opened && permissions.canPost && !entry.open && (
          <button
            type="button"
            style={{ marginLeft: "auto" }}
            onClick={() => entry.set({ ...entry, open: true })}
          >
            New entry
          </button>
        )}
      </div>

      {!overview?.opened && (
        <p style={{ color: "var(--text-muted)", fontSize: 14 }}>
          The books are not open yet. Post the opening balances on the Overview tab before
          recording entries; automatic postings wait for the same step.
        </p>
      )}

      {overview?.opened && !permissions.canPost && (
        <p style={{ color: "var(--text-muted)", fontSize: 14 }}>
          Recording entries needs the accounting.post permission; you can still read the journal.
        </p>
      )}

      {entry.open && (
        <div className="form-grid" style={{ margin: "0 0 16px", padding: 12, border: "1px solid var(--border)", borderRadius: 8 }}>
          <label style={{ fontSize: 13, color: "var(--text-muted)" }}>
            Date
            <input
              type="date"
              aria-label="Entry date"
              value={entry.entryDate}
              max={todayIso()}
              onChange={(e) => entry.set({ ...entry, entryDate: e.target.value })}
            />
          </label>
          <label style={{ fontSize: 13, color: "var(--text-muted)" }}>
            Narration
            <input
              aria-label="Entry narration"
              value={entry.narration}
              onChange={(e) => entry.set({ ...entry, narration: e.target.value })}
              placeholder="What this entry records"
            />
          </label>
          <input
            aria-label="Entry reference"
            placeholder="Reference (optional)"
            value={entry.reference}
            onChange={(e) => entry.set({ ...entry, reference: e.target.value })}
          />
          <div className="form-grid__full">
            <JournalLinesEditor
              accounts={model.activeAccounts}
              lines={entry.lines}
              onChange={(lines) => entry.set({ ...entry, lines })}
              disabled={busy}
            />
          </div>
          {entryLocked && (
            <p
              id="entry-locked-warning"
              role="status"
              className="form-grid__full"
              style={{ margin: 0, fontSize: 13, color: "var(--warning)", fontWeight: 600 }}
            >
              {monthLabel(entry.entryDate)} is locked, so this entry cannot be posted. Choose a
              date in an open month, or unlock the month under Period locks.
            </p>
          )}
          <div className="form-grid__full toolbar">
            <button
              type="button"
              disabled={busy || entryLocked}
              aria-describedby={entryLocked ? "entry-locked-warning" : undefined}
              onClick={entry.submit}
            >
              {busy ? "Posting…" : "Post entry"}
            </button>
            <button
              type="button"
              disabled={busy}
              onClick={() =>
                entry.set({ ...entry, open: false, narration: "", reference: "", lines: emptyJournal() })
              }
            >
              Cancel
            </button>
          </div>
        </div>
      )}

      {model.entriesLoading && <p>Loading entries…</p>}

      {!model.entriesLoading && entries && (
        <>
          <Table>
            <thead>
              <tr>
                <th>Date</th>
                <th>Narration</th>
                <th>Source</th>
                <th>Amount</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {entries.items.map((item) => (
                <EntryRow
                  key={item.id}
                  item={item}
                  reversed={reversedIds.has(item.id)}
                  isReversal={item.source === "reversal"}
                  isOpening={item.source === "opening"}
                  canReverse={permissions.canReverse}
                  reversal={reversal}
                  busy={busy}
                />
              ))}
              {entries.items.length === 0 && (
                <tr>
                  <td colSpan={5}>No entries match these filters.</td>
                </tr>
              )}
            </tbody>
          </Table>

          <p style={{ fontSize: 13, color: "var(--text-muted)" }}>
            Debits on this page: ₦{formatMoney(totalDebit)}
          </p>

          {entries.total > 0 && (
            <Pagination
              skip={entries.skip}
              limit={entries.limit}
              total={entries.total}
              onChange={model.paging.goToPage}
            />
          )}
        </>
      )}
    </>
  );
}

function EntryRow({
  item,
  reversed,
  isReversal,
  isOpening,
  canReverse,
  reversal,
  busy,
}: {
  item: CashbookEntry;
  reversed: boolean;
  isReversal: boolean;
  isOpening: boolean;
  canReverse: boolean;
  reversal: CashbookPageModel["reversal"];
  busy: boolean;
}) {
  const total = item.lines.reduce((sum, line) => sum + Number(line.debit), 0);
  const active = reversal.value?.entryId === item.id;

  return (
    <>
      <tr>
        <td>{item.entry_date}</td>
        <td>
          {item.narration}
          {item.reference ? (
            <div style={{ fontSize: 12, color: "var(--text-muted)" }}>Ref {item.reference}</div>
          ) : null}
        </td>
        <td>
          {SOURCE_LABELS[item.source]}
          {reversed ? (
            <span className="badge badge--neutral" style={{ marginLeft: 6 }}>
              Reversed
            </span>
          ) : null}
        </td>
        <td>₦{formatMoney(total)}</td>
        <td>
          {canReverse && !isReversal && !isOpening && !reversed && !active && (
            <button
              type="button"
              className="link-button"
              onClick={() => reversal.request({ entryId: item.id, narration: item.narration })}
            >
              Reverse
            </button>
          )}
          {reversed && <span style={{ fontSize: 12, color: "var(--text-muted)" }}>Already reversed</span>}
        </td>
      </tr>
      <tr>
        <td colSpan={5} style={{ paddingTop: 0, borderBottom: "1px solid var(--border)" }}>
          <ul style={{ margin: 0, paddingLeft: 18, fontSize: 12, color: "var(--text-muted)" }}>
            {item.lines.map((line) => (
              <li key={line.id}>
                {Number(line.debit) > 0 ? "Dr" : "Cr"} {line.account_code} {line.account_name} — ₦
                {formatMoney(Number(line.debit) > 0 ? line.debit : line.credit)}
              </li>
            ))}
          </ul>
        </td>
      </tr>
      {active && reversal.value ? (
        <tr>
          <td colSpan={5}>
            <div className="form-grid">
              <p className="form-grid__full" style={{ margin: 0, fontSize: 13 }}>
                Reversing <strong>{item.narration}</strong> posts the mirror entry; nothing is deleted.
              </p>
              <textarea
                className="form-grid__full"
                aria-label="Reversal reason"
                placeholder="Why is this entry being reversed?"
                rows={2}
                value={reversal.value.reason}
                onChange={(e) => reversal.setReason(e.target.value)}
                disabled={busy}
              />
              <div className="form-grid__full toolbar">
                <button type="button" disabled={busy} onClick={reversal.submit}>
                  {busy ? "Reversing…" : "Post reversal"}
                </button>
                <button type="button" disabled={busy} onClick={reversal.cancel}>
                  Cancel
                </button>
              </div>
            </div>
          </td>
        </tr>
      ) : null}
    </>
  );
}
