import { useState } from "react";

import type {
  LoanLineCategory,
  PayrollDeductionLineCategory,
  PayrollDeductionLineInput,
} from "@/lib/api";
import { currentMonth } from "@/lib/month";

import type { DeductionsPageModel } from "../hooks/useDeductionsPage";
import { formatMoney, loanLineName } from "../labels";

interface OtherLine {
  label: string;
  amount: string;
}

interface LoanRow {
  key: string;
  loanId: string;
  category: LoanLineCategory;
  loanName: string;
  label: string;
}

// One loan can owe two things in the same month -- this month's instalment
// and a catch-up of the instalments before it -- so a row is keyed by loan
// AND kind, never by loan alone.
function loanRowKey(loanId: string, category: LoanLineCategory): string {
  return `${loanId}:${category}`;
}

function isLoanLine(category: PayrollDeductionLineCategory): category is LoanLineCategory {
  return category === "loan_repayment" || category === "loan_arrears";
}

export default function DeductionForm({
  form,
  busy,
}: {
  form: DeductionsPageModel["form"];
  busy: boolean;
}) {
  const editing = form.editing;
  const prefill = form.prefill;
  // Entering from the queue means the server already said what this member
  // owes, including whether a catch-up is one of the lines.
  const fromQueue = Boolean(prefill) && !editing;

  const [memberId, setMemberId] = useState(editing?.member_id ?? prefill?.memberId ?? "");
  const [month, setMonth] = useState(
    editing ? editing.deduction_month.slice(0, 7) : prefill?.month ?? currentMonth()
  );
  const [reference, setReference] = useState(editing?.payroll_reference ?? "");
  const [note, setNote] = useState(editing?.note ?? "");

  const existingContribution = editing?.lines.find(
    (line) => line.category === "monthly_contribution"
  );
  const [contribution, setContribution] = useState(
    existingContribution?.amount ?? prefill?.contribution ?? ""
  );

  const [otherLines, setOtherLines] = useState<OtherLine[]>(
    (editing?.lines ?? [])
      .filter((line) => line.category === "other")
      .map((line) => ({ label: line.label ?? "", amount: line.amount }))
  );

  const [loanAmounts, setLoanAmounts] = useState<Record<string, string>>(() => {
    if (editing) {
      const existing: Record<string, string> = {};
      for (const line of editing.lines) {
        if (line.loan_id && isLoanLine(line.category)) {
          existing[loanRowKey(line.loan_id, line.category)] = line.amount;
        }
      }
      return existing;
    }
    if (prefill) {
      return Object.fromEntries(prefill.loanLines.map((line) => [line.key, line.amount]));
    }
    return {};
  });

  // Whether to offer a catch-up at all is the officer's call when the figure
  // did not come from the queue, so that row starts hidden.
  const [catchUpLoans, setCatchUpLoans] = useState<string[]>([]);

  const [localError, setLocalError] = useState<string | null>(null);

  const activeLoans = memberId ? form.loansForMember(memberId) : [];
  const activeLoanIds = new Set(activeLoans.map((loan) => loan.id));
  // Existing loan lines stay visible even if that loan is no longer active,
  // so editing never silently drops an allocation.
  const staleLoanRows: LoanRow[] = (editing?.lines ?? []).flatMap((line) => {
    if (!line.loan_id || !isLoanLine(line.category) || activeLoanIds.has(line.loan_id)) {
      return [];
    }
    const loanName = line.loan_type_name ?? "Loan";
    return [
      {
        key: loanRowKey(line.loan_id, line.category),
        loanId: line.loan_id,
        category: line.category,
        loanName,
        label: `${loanLineName(line.category, loanName)} — no longer active`,
      },
    ];
  });

  // Queue entry renders the server's expected loan lines directly, so the
  // amounts are right even when the Loans module is disabled and the local
  // loan lookup is empty. Blank/edit entry uses the member's active loans.
  const loanRows: LoanRow[] =
    fromQueue && prefill
      ? prefill.loanLines.map((line) => ({
          key: line.key,
          loanId: line.loanId,
          category: line.category,
          loanName: line.loanName,
          label: line.label,
        }))
      : [
          ...activeLoans.flatMap((loan): LoanRow[] => {
            const rows: LoanRow[] = [
              {
                key: loanRowKey(loan.id, "loan_repayment"),
                loanId: loan.id,
                category: "loan_repayment",
                loanName: loan.loan_type_name,
                label: `${loan.loan_type_name} — balance ${formatMoney(loan.balance)}`,
              },
            ];
            if (catchUpLoans.includes(loan.id)) {
              rows.push({
                key: loanRowKey(loan.id, "loan_arrears"),
                loanId: loan.id,
                category: "loan_arrears",
                loanName: loan.loan_type_name,
                label: loanLineName("loan_arrears", loan.loan_type_name),
              });
            }
            return rows;
          }),
          ...staleLoanRows,
        ];

  // Only financial members owe the monthly contribution. The queue carries
  // the authoritative status; blank entry falls back to the member lookup.
  const selectedMember = form.members.find((member) => member.id === memberId);
  const isFinancial = prefill
    ? prefill.memberStatus === "financial"
    : selectedMember
      ? selectedMember.status === "financial"
      : true;
  // Narrowed conflict policy: a linked officer MAY record the expected
  // amounts, but cannot type a different amount or add a discretionary
  // 'other' line, and cannot confirm. Lock the inputs to the expectation.
  const isConflicted = Boolean(prefill?.conflicted || selectedMember?.conflicted);

  function changeMember(value: string) {
    setMemberId(value);
    setLoanAmounts({});
    setCatchUpLoans([]);
  }

  function updateOtherLine(index: number, patch: Partial<OtherLine>) {
    setOtherLines((current) =>
      current.map((line, i) => (i === index ? { ...line, ...patch } : line))
    );
  }

  function submit() {
    const lines: PayrollDeductionLineInput[] = [];

    if (isFinancial && Number(contribution) > 0) {
      lines.push({ category: "monthly_contribution", amount: Number(contribution) });
    }

    for (const row of loanRows) {
      const amount = Number(loanAmounts[row.key] || 0);
      if (amount > 0) {
        lines.push({ category: row.category, loan_id: row.loanId, amount });
      }
    }

    for (const [index, other] of otherLines.entries()) {
      const label = other.label.trim();
      const amount = Number(other.amount || 0);
      if (!label && amount === 0) continue;
      if (!label || amount <= 0) {
        setLocalError(`Other deduction ${index + 1} needs both a label and an amount.`);
        return;
      }
      lines.push({ category: "other", label, amount });
    }

    if (!editing && !memberId) {
      setLocalError("Choose a member.");
      return;
    }
    if (!lines.length) {
      setLocalError(
        isConflicted
          ? "No expected amounts to record. Use the Enter queue, which fills in what this member owes."
          : "Add at least one deduction line."
      );
      return;
    }

    setLocalError(null);
    if (editing) {
      form.save(
        {
          deduction_month: month,
          payroll_reference: reference.trim() || null,
          note: note.trim() || null,
          lines,
        },
        editing.id
      );
    } else {
      form.save({
        member_id: memberId,
        deduction_month: month,
        payroll_reference: reference.trim() || undefined,
        note: note.trim() || undefined,
        lines,
      });
    }
  }

  const heading = editing
    ? "Edit draft deduction"
    : prefill
      ? `Enter deduction — ${prefill.memberName}`
      : "New deduction";

  return (
    <section
      style={{
        border: "1px solid #ccc",
        borderRadius: 6,
        padding: 16,
        marginBottom: 20,
        background: "#fafafa",
      }}
    >
      <h2 style={{ marginTop: 0 }}>{heading}</h2>

      <div style={{ display: "flex", gap: 12, flexWrap: "wrap", marginBottom: 12 }}>
        <label>
          <span style={{ display: "block", fontSize: 12, color: "#555" }}>Member</span>
          <select
            aria-label="Member"
            value={memberId}
            disabled={Boolean(editing) || Boolean(prefill)}
            onChange={(e) => changeMember(e.target.value)}
          >
            <option value="">Select a member...</option>
            {form.members.map((member) => (
              <option key={member.id} value={member.id}>
                {member.psn} — {member.name}
              </option>
            ))}
            {prefill && !form.members.some((member) => member.id === prefill.memberId) && (
              <option value={prefill.memberId}>{prefill.memberName}</option>
            )}
          </select>
          {!form.members.length && !prefill && (
            <span style={{ display: "block", fontSize: 12, color: "#a33", marginTop: 4 }}>
              No members available — the Members module may be disabled.
            </span>
          )}
          {isConflicted && (
            <span style={{ display: "block", fontSize: 12, color: "#b45309", marginTop: 4 }}>
              ⚠ Conflict of interest — you can record the expected amounts, but another officer must
              approve any different amount and confirm the deduction.
            </span>
          )}
        </label>
        <label>
          <span style={{ display: "block", fontSize: 12, color: "#555" }}>Payroll month</span>
          <input
            type="month"
            aria-label="Deduction month"
            value={month}
            disabled={Boolean(prefill) && !editing}
            onChange={(e) => setMonth(e.target.value)}
          />
        </label>

        <label>
          <span style={{ display: "block", fontSize: 12, color: "#555" }}>Payroll reference</span>
          <input
            aria-label="Payroll reference"
            value={reference}
            onChange={(e) => setReference(e.target.value)}
            placeholder="e.g. PAY-2026-11"
          />
        </label>
      </div>

      <label style={{ display: "block", marginBottom: 12 }}>
        <span style={{ display: "block", fontSize: 12, color: "#555" }}>Note</span>
        <input
          aria-label="Note"
          value={note}
          onChange={(e) => setNote(e.target.value)}
          style={{ width: "100%" }}
        />
      </label>

      {isFinancial ? (
        <>
          <h3 style={{ marginBottom: 4 }}>Monthly contribution</h3>
          <input
            aria-label="Monthly contribution"
            type="number"
            min="0"
            step="0.01"
            value={contribution}
            disabled={isConflicted}
            onChange={(e) => setContribution(e.target.value)}
            placeholder="0.00"
          />
        </>
      ) : (
        <p style={{ color: "#666", fontSize: 14 }}>
          Non-financial member — no monthly contribution. Anything they still
          owes goes under other deductions below.
        </p>
      )}

      <h3 style={{ marginBottom: 4, marginTop: 16 }}>Loan repayments</h3>
      {!memberId && <p style={{ color: "#666" }}>Select a member to see their active loans.</p>}
      {memberId && !loanRows.length && (
        <p style={{ color: "#666" }}>This member has no loan instalment due.</p>
      )}
      {loanRows.map((row) => (
        <div key={row.key} style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 6 }}>
          <span style={{ minWidth: 260 }}>{row.label}</span>
          <input
            aria-label={
              row.category === "loan_arrears"
                ? `Arrears catch-up for ${row.loanName}`
                : `Repayment for ${row.loanName}`
            }
            type="number"
            min="0"
            step="0.01"
            value={loanAmounts[row.key] ?? ""}
            disabled={isConflicted}
            onChange={(e) =>
              setLoanAmounts((current) => ({ ...current, [row.key]: e.target.value }))
            }
            placeholder="0.00"
          />
          {!fromQueue &&
            row.category === "loan_repayment" &&
            activeLoanIds.has(row.loanId) &&
            !catchUpLoans.includes(row.loanId) && (
              <button
                onClick={() => setCatchUpLoans((loans) => [...loans, row.loanId])}
              >
                Add arrears catch-up
              </button>
            )}
        </div>
      ))}

      {!isConflicted && (
        <>
          <h3 style={{ marginBottom: 4, marginTop: 16 }}>Other deductions</h3>
          {otherLines.map((line, index) => (
            <div key={index} style={{ display: "flex", gap: 8, marginBottom: 6 }}>
              <input
                aria-label={`Other deduction ${index + 1} label`}
                value={line.label}
                onChange={(e) => updateOtherLine(index, { label: e.target.value })}
                placeholder="Label, e.g. Welfare"
              />
              <input
                aria-label={`Other deduction ${index + 1} amount`}
                type="number"
                min="0"
                step="0.01"
                value={line.amount}
                onChange={(e) => updateOtherLine(index, { amount: e.target.value })}
                placeholder="0.00"
              />
              <button
                onClick={() => setOtherLines((current) => current.filter((_, i) => i !== index))}
              >
                Remove
              </button>
            </div>
          ))}
          <button onClick={() => setOtherLines((current) => [...current, { label: "", amount: "" }])}>
            Add other deduction
          </button>
        </>
      )}

      {localError && <p style={{ color: "crimson", fontWeight: 600 }}>{localError}</p>}

      <div style={{ display: "flex", gap: 8, marginTop: 16 }}>
        <button
          disabled={busy}
          onClick={submit}
          title={
            isConflicted
              ? "You can record the expected amounts; another officer must approve any different amount and confirm the deduction"
              : undefined
          }
        >
          {editing ? "Save draft" : "Create draft"}
        </button>
        <button disabled={busy} onClick={form.close}>
          Cancel
        </button>
      </div>
    </section>
  );
}