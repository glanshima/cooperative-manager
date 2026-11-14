import Table from "@/components/ui/Table";
import { ConflictMarker } from "@/components/ui/ConflictMarker";
import type { PayrollDeduction } from "@/lib/api";

import type { DeductionActionKind, DeductionsPageModel } from "../hooks/useDeductionsPage";
import { STATUS_COLORS, STATUS_LABELS, formatMoney } from "../labels";

const cellStyle = { padding: "6px 8px", borderBottom: "1px solid #ddd", verticalAlign: "top" };

function ReasonNote({ deduction }: { deduction: PayrollDeduction }) {
  const note =
    deduction.void_reason ||
    deduction.not_deducted_reason ||
    deduction.return_reason ||
    null;
  if (!note) return null;
  return (
    <div style={{ fontSize: 12, color: "#666", maxWidth: 220 }}>{note}</div>
  );
}

function RowActions({
  deduction,
  disabled,
  onAction,
  onEdit,
}: {
  deduction: PayrollDeduction;
  disabled: boolean;
  onAction: (action: DeductionActionKind, ids: string[]) => void;
  onEdit: (deduction: PayrollDeduction) => void;
}) {
  // The record is in the ledger and in the month's totals; this officer
  // simply isn't the one who may move it along.
  if (deduction.conflicted) return <ConflictMarker />;

  const id = [deduction.id];
  return (
    <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
      {deduction.status === "draft" && (
        <>
          <button disabled={disabled} onClick={() => onEdit(deduction)}>
            Edit
          </button>
          <button disabled={disabled} onClick={() => onAction("submit", id)}>
            Submit
          </button>
          <button disabled={disabled} onClick={() => onAction("not_deducted", id)}>
            Not deducted
          </button>
        </>
      )}
      {deduction.status === "submitted" && (
        <>
          <button disabled={disabled} onClick={() => onAction("confirm", id)}>
            Confirm
          </button>
          <button disabled={disabled} onClick={() => onAction("return_to_draft", id)}>
            Return to draft
          </button>
          <button disabled={disabled} onClick={() => onAction("not_deducted", id)}>
            Not deducted
          </button>
        </>
      )}
      {deduction.status !== "void" && (
        <button disabled={disabled} onClick={() => onAction("void", id)}>
          Void
        </button>
      )}
    </div>
  );
}

export default function DeductionsTable({
  table,
  actions,
  busy,
  search = "",
  onEdit,
}: {
  table: DeductionsPageModel["table"];
  actions: DeductionsPageModel["actions"];
  busy: boolean;
  search?: string;
  onEdit: (deduction: PayrollDeduction) => void;
}) {
  // Bulk actions are writes, so conflicted rows aren't offered for
  // selection at all -- they'd only come back as per-record 409s.
  const ids = table.items.filter((deduction) => !deduction.conflicted).map((deduction) => deduction.id);
  const allSelected = ids.length > 0 && ids.every((id) => table.selected.includes(id));

  if (!table.items.length) {
    return (
      <p>
        {search.trim()
          ? `No deduction records match “${search.trim()}” for this month and status.`
          : "No deduction records for this month and status."}
      </p>
    );
  }

  return (
    <Table>
      <thead>
        <tr style={{ textAlign: "left", background: "#f4f4f4" }}>
          <th style={cellStyle}>
            <input
              type="checkbox"
              aria-label="Select all deductions"
              checked={allSelected}
              onChange={() => table.toggleAll(ids)}
            />
          </th>
          <th style={cellStyle}>Member</th>
          <th style={cellStyle}>Contribution</th>
          <th style={cellStyle}>Loans</th>
          <th style={cellStyle}>Arrears</th>
          <th style={cellStyle}>Other</th>
          <th style={cellStyle}>Total</th>
          <th style={cellStyle}>Status</th>
          <th style={cellStyle}>Actions</th>
        </tr>
      </thead>
      <tbody>
        {table.items.map((deduction) => (
          <tr key={deduction.id}>
            <td style={cellStyle}>
              <input
                type="checkbox"
                aria-label={`Select ${deduction.member_psn ?? deduction.member_id}`}
                checked={table.selected.includes(deduction.id)}
                disabled={deduction.conflicted}
                onChange={() => table.toggleSelected(deduction.id)}
              />
            </td>
            <td style={cellStyle}>
              <strong>{deduction.member_name ?? "Unknown member"}</strong>
              <div style={{ fontSize: 12, color: "#555" }}>{deduction.member_psn?.replace("MCT-", "") ?? ""}</div>
              {deduction.payroll_reference && (
                <div style={{ fontSize: 12, color: "#555" }}>Ref {deduction.payroll_reference}</div>
              )}
            </td>
            <td style={cellStyle}>{formatMoney(deduction.contribution_total)}</td>
            <td style={cellStyle}>{formatMoney(deduction.loan_total)}</td>
            <td style={cellStyle}>{formatMoney(deduction.arrears_total)}</td>
            <td style={cellStyle}>{formatMoney(deduction.other_total)}</td>
            <td style={cellStyle}>
              <strong>{formatMoney(deduction.grand_total)}</strong>
            </td>
            <td style={cellStyle}>
              <span style={{ color: STATUS_COLORS[deduction.status], fontWeight: 600 }}>
                {STATUS_LABELS[deduction.status]}
              </span>
              <ReasonNote deduction={deduction} />
            </td>
            <td style={cellStyle}>
              <RowActions
                deduction={deduction}
                disabled={busy}
                onAction={actions.request}
                onEdit={onEdit}
              />
            </td>
          </tr>
        ))}
      </tbody>
    </Table>
  );
}
