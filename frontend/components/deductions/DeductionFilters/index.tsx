import { monthLabel } from "@/lib/month";

import { STATUS_LABELS, formatMoney } from "../labels";
import type { DeductionsPageModel } from "../hooks/useDeductionsPage";

const STATUS_OPTIONS = Object.entries(STATUS_LABELS) as [string, string][];

export default function DeductionFilters({
  filters,
  totals,
  onCreate,
  onPrint,
}: {
  filters: DeductionsPageModel["filters"];
  totals: DeductionsPageModel["totals"];
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

        <button onClick={onCreate}>New deduction</button>
        <button onClick={onPrint}>Print schedule</button>

        {totals && (
          <span style={{ marginLeft: "auto", color: "#333", fontSize: 14 }}>
            {monthLabel(filters.month)} — contribution {formatMoney(totals.contribution_total)}, loans{" "}
            {formatMoney(totals.loan_total)}, other {formatMoney(totals.other_total)} — total{" "}
            <strong>{formatMoney(totals.grand_total)}</strong>
          </span>
        )}
      </div>
    </section>
  );
}
