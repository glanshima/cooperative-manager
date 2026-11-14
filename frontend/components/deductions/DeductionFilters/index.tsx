import { monthLabel } from "@/lib/month";

import { STATUS_LABELS, formatMoney } from "../labels";
import type { DeductionsPageModel } from "../hooks/useDeductionsPage";

const STATUS_OPTIONS = Object.entries(STATUS_LABELS) as [string, string][];

export default function DeductionFilters({
  filters,
  totals,
  resultCount,
  onCreate,
  onPrint,
}: {
  filters: DeductionsPageModel["filters"];
  totals: DeductionsPageModel["totals"];
  resultCount: number;
  onCreate: () => void;
  onPrint: () => void;
}) {
  return (
    <section style={{ marginBottom: 16 }}>
      <div style={{ display: "flex", gap: 12, alignItems: "flex-end", flexWrap: "wrap" }}>
        <label>
          <span style={{ display: "block", fontSize: 12, color: "#555" }}>Payroll month</span>
          <input
            type="month"
            value={filters.month}
            onChange={(e) => filters.setMonth(e.target.value)}
            aria-label="Payroll month"
          />
        </label>

        <label>
          <span style={{ display: "block", fontSize: 12, color: "#555" }}>Status</span>
          <select
            value={filters.status}
            onChange={(e) => filters.setStatus(e.target.value as any)}
            aria-label="Status"
          >
            <option value="all">All statuses</option>
            {STATUS_OPTIONS.map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </label>

        <label>
          <span style={{ display: "block", fontSize: 12, color: "#555" }}>Search ledger</span>
          <input
            type="search"
            value={filters.search}
            onChange={(e) => filters.setSearch(e.target.value)}
            aria-label="Search ledger by name, PSN, payroll reference or note"
            placeholder="Name, PSN, reference or note"
          />
        </label>
        {filters.search && (
          <button type="button" onClick={() => filters.setSearch("")}>
            Clear search
          </button>
        )}

        <button onClick={onCreate}>New deduction</button>
        <button onClick={onPrint}>Print schedule</button>

        {totals && (
          <span style={{ marginLeft: "auto", color: "#333", fontSize: 14 }}>
            {monthLabel(filters.month)} — contribution {formatMoney(totals.contribution_total)}, loans{" "}
            {formatMoney(totals.loan_total)}, arrears {formatMoney(totals.arrears_total)}, other{" "}
            {formatMoney(totals.other_total)} — total <strong>{formatMoney(totals.grand_total)}</strong>
          </span>
        )}
      </div>

      {filters.search.trim() && (
        <p role="status" style={{ margin: "8px 0 0", fontSize: 14 }}>
          {resultCount} record{resultCount === 1 ? "" : "s"} match “{filters.search.trim()}”. The month
          totals above include every record; the list below is filtered.
        </p>
      )}
    </section>
  );
}
