"use client";

import type {
  DeductionWorklistEntryState,
  DeductionWorklistItem,
  DeductionWorklistOut,
} from "@/lib/api";
import { monthLabel } from "@/lib/month";
import { ConflictMarker } from "@/components/ui/ConflictMarker";
import Pagination from "@/components/ui/Pagination";

import type { DeductionsPageModel } from "../hooks/useDeductionsPage";
import { STATUS_LABELS, formatMoney } from "../labels";
import type { PayrollDeductionLineCategory } from "@/lib/api/deductions";

type LoanLineCategory = "loan_repayment" | "loan_arrears";

function loanLineName(category: LoanLineCategory, loanTypeName?: string | null): string {
  const name = loanTypeName ?? "Loan";
  return category === "loan_arrears" ? `Arrears on ${name}` : name;
}

function monthsBehind(count: number): string {
  return `${count} month${count === 1 ? "" : "s"} behind`;
}

const SEGMENTS: {
  value: DeductionWorklistEntryState;
  label: string;
  count: (data: DeductionWorklistOut) => number;
}[] = [
  { value: "pending", label: "Pending", count: (data) => data.pending_count },
  { value: "entered", label: "Entered", count: (data) => data.entered_count },
  { value: "all", label: "All", count: (data) => data.due_count },
];

const EMPTY_COPY: Record<DeductionWorklistEntryState, (month: string) => string> = {
  pending: (label) =>
    `Nothing left to enter for ${label}. Every member who owes a contribution or loan instalment has been entered.`,
  entered: (label) => `Nothing has been entered for ${label} yet.`,
  all: (label) => `Nothing is due for ${label}.`,
};

function ExpectedLines({ item }: { item: DeductionWorklistItem }) {
  return (
    <ul style={{ margin: "8px 0 0 0", padding: 0, listStyle: "none", fontSize: 13 }}>
      {item.lines.map((line, index) => (
        <li key={index} style={{ padding: "2px 0" }}>
          {line.category === "monthly_contribution" && (
            <span>Contribution ₦{formatMoney(line.amount)}</span>
          )}
          {(line.category === "loan_repayment" || line.category === "loan_arrears") && (
            <span style={line.category === "loan_arrears" ? { color: "#b45309" } : undefined}>
              {loanLineName(line.category, line.loan_type_name)} ₦{formatMoney(line.amount)}
              {line.category === "loan_arrears" && line.months_behind > 0 && (
                <span> · {monthsBehind(line.months_behind)}</span>
              )}
            </span>
          )}
        </li>
      ))}
    </ul>
  );
}

export default function DeductionWorklist({
  worklist,
  month,
  setMonth,
  onAddAny,
  onPageSizeChange,
  busy,
}: {
  worklist: DeductionsPageModel["worklist"];
  month: string;
  setMonth: (value: string) => void;
  onAddAny: () => void;
  onPageSizeChange: (value: number) => void;
  busy: boolean;
}) {
  const data = worklist.data;

  return (
    <section style={{ marginBottom: 20 }}>
      <div style={{ display: "flex", gap: 12, alignItems: "flex-end", flexWrap: "wrap", marginBottom: 12 }}>
        <label>
          <span style={{ display: "block", fontSize: 12, color: "#555" }}>Payroll month</span>
          <input
            type="month"
            value={month}
            onChange={(e) => setMonth(e.target.value)}
            aria-label="Payroll month"
          />
        </label>
        <div role="group" aria-label="Queue" style={{ display: "flex", gap: 4 }}>
          {SEGMENTS.map((segment) => (
            <button
              key={segment.value}
              onClick={() => worklist.setEntryState(segment.value)}
              aria-pressed={worklist.entryState === segment.value}
              style={{ fontWeight: worklist.entryState === segment.value ? 700 : 400 }}
            >
              {segment.label}
              {data ? ` (${segment.count(data)})` : ""}
            </button>
          ))}
        </div>
        <button onClick={onAddAny}>Add any member</button>
        <button onClick={() => worklist.refresh()} disabled={worklist.loading}>
          {worklist.loading ? "Loading…" : "Refresh"}
        </button>
        {data && (
          <span style={{ marginLeft: "auto", fontSize: 14, color: "#333" }}>
            {monthLabel(month)} — <strong>{data.due_count}</strong> due ·{" "}
            <strong>{data.entered_count}</strong> entered · ₦{formatMoney(data.expected_total)} still to
            enter
          </span>
        )}
      </div>

      {worklist.lastEntered && (
        <p
          role="status"
          style={{ background: "#d4edda", border: "1px solid #c3e6cb", borderRadius: 4, padding: "8px 12px" }}
        >
          Entered {worklist.lastEntered.memberName}.{" "}
          <button onClick={worklist.undo} disabled={busy}>
            Undo
          </button>
        </p>
      )}

      {worklist.error && <p style={{ color: "crimson" }}>Error loading queue: {worklist.error}</p>}
      {worklist.loading && !data && <p>Loading queue…</p>}

      {data && data.items.length === 0 && !worklist.loading && (
        <p style={{ color: "#666" }}>{EMPTY_COPY[worklist.entryState](monthLabel(month))}</p>
      )}

      {data?.items.map((item) => {
        const entered = Boolean(item.deduction_id);
        return (
          <div
            key={item.member_id}
            style={{ border: "1px solid #eee", borderRadius: 4, padding: 12, marginBottom: 10 }}
          >
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: 8 }}>
              <strong>
                {item.member_name} · PSN {item.member_psn?.replace("MCT-", "") ?? ""}
                {item.conflicted && <> <ConflictMarker /></>}
              </strong>
              <span style={{ fontSize: 13, color: "#555" }}>
                {item.member_status === "financial" ? "Financial" : "Non-financial"}
                {item.membership_exit_date && ` · exited ${item.membership_exit_date}`}
              </span>
            </div>

            <ExpectedLines item={item} />

            {item.warnings.length > 0 && (
              <ul style={{ margin: "6px 0 0 0", padding: "0 0 0 18px", fontSize: 12, color: "#b45309" }}>
                {item.warnings.map((warning, index) => (
                  <li key={index}>{warning}</li>
                ))}
              </ul>
            )}

            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: 10 }}>
              <span style={{ fontSize: 14 }}>
                Expected <strong>₦{formatMoney(item.expected_total)}</strong>
              </span>
              {entered ? (
                <span style={{ fontSize: 13, color: "#555" }}>
                  Entered · {item.deduction_status ? STATUS_LABELS[item.deduction_status] : ""}
                </span>
              ) : (
                <button disabled={busy} onClick={() => worklist.openItem(item)}>
                  {item.conflicted ? "Enter expected amounts" : "Enter"}
                </button>
              )}
            </div>
          </div>
        );
      })}

      {data && data.total > 0 && (
        <Pagination
          skip={worklist.pagination.skip}
          limit={worklist.pagination.limit}
          total={data.total}
          onChange={worklist.pagination.goToPage}
          onPageSizeChange={onPageSizeChange}
        />
      )}
    </section>
  );
}
