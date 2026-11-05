import { useState } from "react";

import type { PayrollDeductionLineInput } from "@/lib/api";

import type { DeductionsPageModel } from "../hooks/useDeductionsPage";
import { currentMonth, formatMoney } from "../labels";

interface OtherLine {
  label: string;
  amount: string;
}

export default function DeductionForm({
  form,
  busy,
}: {
  form: DeductionsPageModel["form"];
  busy: boolean;
}) {
  const editing = form.editing;

  const [memberId, setMemberId] = useState(editing?.member_id ?? "");
  const [month, setMonth] = useState(
    editing ? editing.deduction_month.slice(0, 7) : currentMonth()
  );
  const [reference, setReference] = useState(editing?.payroll_reference ?? "");
  const [note, setNote] = useState(editing?.note ?? "");

  const existingContribution = editing?.lines.find(
    (line) => line.category === "monthly_contribution"
  );
  const [contribution, setContribution] = useState(existingContribution?.amount ?? "");

  const [otherLines, setOtherLines] = useState<OtherLine[]>(
    (editing?.lines ?? [])
      .filter((line) => line.category === "other")
      .map((line) => ({ label: line.label ?? "", amount: line.amount }))
  );

  const [loanAmounts, setLoanAmounts] = useState<Record<string, string>>(() => {
    const existing: Record<string, string> = {};
    for (const line of editing?.lines ?? []) {
      if (line.category === "loan_repayment" && line.loan_id) {
        existing[line.loan_id] = line.amount;
      }
    }
    return existing;
  });

  const [localError, setLocalError] = useState<string | null>(null);

  const activeLoans = memberId ? form.loansForMember(memberId) : [];
  const activeLoanIds = new Set(activeLoans.map((loan) => loan.id));
  // Existing loan lines stay visible even if that loan is no longer active,
  // so editing never silently drops an allocation.
  const staleLoanLines = (editing?.lines ?? []).filter(
    (line) => line.category === "loan_repayment" && line.loan_id && !activeLoanIds.has(line.loan_id)
  );

  function changeMember(value: string) {
    setMemberId(value);
    setLoanAmounts({});
  }

  function updateOtherLine(index: number, patch: Partial<OtherLine>) {
    setOtherLines((current) =>
      current.map((line, i) => (i === index ? { ...line, ...patch } : line))
    );
  }

  function submit() {
    const lines: PayrollDeductionLineInput[] = [];

    if (Number(contribution) > 0) {
      lines.push({ category: "monthly_contribution", amount: Number(contribution) });
    }

    for (const loan of activeLoans) {
      const amount = Number(loanAmounts[loan.id] || 0);
      if (amount > 0) {
        lines.push({ category: "loan_repayment", loan_id: loan.id, amount });
      }
    }
    for (const line of staleLoanLines) {
      const amount = Number(loanAmounts[line.loan_id!] || 0);
      if (amount > 0) {
        lines.push({ category: "loan_repayment", loan_id: line.loan_id!, amount });
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
      setLocalError("Add at least one deduction line.");
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
      <h2 style={{ marginTop: 0 }}>{editing ? "Edit draft deduction" : "New deduction"}</h2>

      <div style={{ display: "flex", gap: 12, flexWrap: "wrap", marginBottom: 12 }}>
        <label>
          <span style={{ display: "block", fontSize: 12, color: "#555" }}>Member</span>
          <select
            aria-label="Member"
            value={memberId}
            disabled={Boolean(editing)}
            onChange={(e) => changeMember(e.target.value)}
          >
            <option value="">Select a member...</option>
            {form.members.map((member) => (
              <option key={member.id} value={member.id}>
                {member.psn} — {member.name}
              </option>
            ))}
          </select>
          {!form.members.length && (
            <span style={{ display: "block", fontSize: 12, color: "#a33", marginTop: 4 }}>
              No members available — the Members module may be disabled.
            </span>
          )}
        </label>
        <label>
          <span style={{ display: "block", fontSize: 12, color: "#555" }}>Payroll month</span>
          <input
            type="month"
            aria-label="Deduction month"
            value={month}
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

      <h3 style={{ marginBottom: 4 }}>Monthly contribution</h3>
      <input
        aria-label="Monthly contribution"
        type="number"
        min="0"
        step="0.01"
        value={contribution}
        onChange={(e) => setContribution(e.target.value)}
        placeholder="0.00"
      />

      <h3 style={{ marginBottom: 4, marginTop: 16 }}>Loan repayments</h3>
      {!memberId && <p style={{ color: "#666" }}>Select a member to see their active loans.</p>}
      {memberId && !activeLoans.length && !staleLoanLines.length && (
        <p style={{ color: "#666" }}>This member has no active loans.</p>
      )}
      {activeLoans.map((loan) => (
        <div key={loan.id} style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 6 }}>
          <span style={{ minWidth: 260 }}>
            {loan.loan_type_name} — balance {formatMoney(loan.balance)}
          </span>
          <input
            aria-label={`Repayment for ${loan.loan_type_name}`}
            type="number"
            min="0"
            step="0.01"
            value={loanAmounts[loan.id] ?? ""}
            onChange={(e) =>
              setLoanAmounts((current) => ({ ...current, [loan.id]: e.target.value }))
            }
            placeholder="0.00"
          />
        </div>
      ))}
      {staleLoanLines.map((line) => (
        <div key={line.id} style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 6 }}>
          <span style={{ minWidth: 260, color: "#a33" }}>
            {line.loan_type_name ?? "Loan"} — no longer active
          </span>
          <input
            aria-label={`Repayment for ${line.loan_type_name ?? "inactive loan"}`}
            type="number"
            min="0"
            step="0.01"
            value={loanAmounts[line.loan_id!] ?? ""}
            onChange={(e) =>
              setLoanAmounts((current) => ({ ...current, [line.loan_id!]: e.target.value }))
            }
            placeholder="0.00"
          />
        </div>
      ))}

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

      {localError && <p style={{ color: "crimson", fontWeight: 600 }}>{localError}</p>}

      <div style={{ display: "flex", gap: 8, marginTop: 16 }}>
        <button disabled={busy} onClick={submit}>
          {editing ? "Save draft" : "Create draft"}
        </button>
        <button disabled={busy} onClick={form.close}>
          Cancel
        </button>
      </div>
    </section>
  );
}
