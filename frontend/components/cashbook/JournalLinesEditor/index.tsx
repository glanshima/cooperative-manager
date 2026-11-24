import { formatMoney } from "@/components/deductions/labels";
import type { CashbookAccount } from "@/lib/api";

import { JournalLineDraft, lineTotals, newJournalLine } from "../journal";

/**
 * The debit/credit rows shared by the opening journal and the manual entry
 * form. Each row is one side only -- typing a debit clears that row's
 * credit -- so a line can never silently carry both.
 */
export default function JournalLinesEditor({
  accounts,
  lines,
  onChange,
  disabled = false,
}: {
  accounts: CashbookAccount[];
  lines: JournalLineDraft[];
  onChange: (lines: JournalLineDraft[]) => void;
  disabled?: boolean;
}) {
  const totals = lineTotals(lines);

  function update(index: number, patch: Partial<JournalLineDraft>) {
    onChange(lines.map((line, i) => (i === index ? { ...line, ...patch } : line)));
  }

  return (
    <div style={{ display: "grid", gap: 8 }}>
      {lines.map((line, index) => (
        <div
          key={line.key}
          style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}
        >
          <select
            aria-label={`Line ${index + 1} account`}
            value={line.accountId}
            onChange={(e) => update(index, { accountId: e.target.value })}
            disabled={disabled}
            style={{ flex: "1 1 220px", minWidth: 180 }}
          >
            <option value="">Choose account…</option>
            {accounts.map((account) => (
              <option key={account.id} value={account.id}>
                {account.code} — {account.name}
              </option>
            ))}
          </select>
          <input
            aria-label={`Line ${index + 1} debit`}
            placeholder="Debit"
            inputMode="decimal"
            value={line.debit}
            onChange={(e) => update(index, { debit: e.target.value, credit: "" })}
            disabled={disabled}
            style={{ width: 110 }}
          />
          <input
            aria-label={`Line ${index + 1} credit`}
            placeholder="Credit"
            inputMode="decimal"
            value={line.credit}
            onChange={(e) => update(index, { credit: e.target.value, debit: "" })}
            disabled={disabled}
            style={{ width: 110 }}
          />
          <button
            type="button"
            onClick={() => onChange(lines.filter((_, i) => i !== index))}
            disabled={disabled || lines.length <= 2}
            title={lines.length <= 2 ? "An entry needs at least two lines." : "Remove line"}
          >
            Remove
          </button>
        </div>
      ))}

      <div className="toolbar" style={{ marginTop: 0 }}>
        <button
          type="button"
          onClick={() => onChange([...lines, newJournalLine()])}
          disabled={disabled}
        >
          Add line
        </button>
        <span style={{ fontSize: 13, color: "var(--text-muted)" }}>
          Debits ₦{formatMoney(totals.debit)} · Credits ₦{formatMoney(totals.credit)}
        </span>
        {totals.balanced ? (
          <span className="badge badge--success">Balanced</span>
        ) : (
          <span className="badge badge--warning">
            Out by ₦{formatMoney(Math.abs(totals.debit - totals.credit))}
          </span>
        )}
      </div>
    </div>
  );
}
