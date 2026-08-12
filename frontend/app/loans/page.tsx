"use client";

import { useEffect, useState } from "react";
import { useAuth } from "../../lib/useAuth";
import {
  Loan,
  LoanInput,
  LoanType,
  LoanTypeInput,
  listLoans,
  createLoan,
  updateLoan,
  deleteLoan,
  listLoanTypes,
  createLoanType,
  updateLoanType,
} from "../../lib/api";
import { listMembers, Member } from "../../lib/api";

const emptyLoanForm: LoanInput = {
  member_id: "",
  loan_type_id: "",
  principal: 0,
  disbursement_date: new Date().toISOString().slice(0, 10),
  notes: "",
};

const emptyTypeForm: LoanTypeInput = {
  name: "",
  interest_rate: 0.15,
  tenure_months: 12,
  flat_charge: 0,
  is_active: true,
  open_for_application: false,
};

export default function LoansPage() {
  const { loading: authLoading, logout } = useAuth({
    requireAuth: true,
    requirePasswordChanged: true,
    requireRole: "admin",
  });

  const [loans, setLoans] = useState<Loan[]>([]);
  const [loanTypes, setLoanTypes] = useState<LoanType[]>([]);
  const [members, setMembers] = useState<Member[]>([]);

  const [loanForm, setLoanForm] = useState<LoanInput>(emptyLoanForm);
  const [typeForm, setTypeForm] = useState<LoanTypeInput>(emptyTypeForm);

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showTypeManager, setShowTypeManager] = useState(false);

  async function refresh() {
    setLoading(true);
    setError(null);
    try {
      const [loansData, typesData, membersData] = await Promise.all([
        listLoans(),
        listLoanTypes(),
        listMembers(),
      ]);
      setLoans(loansData);
      setLoanTypes(typesData);
      setMembers(membersData);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (!authLoading) refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [authLoading]);

  async function handleDisburse(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      await createLoan(loanForm);
      setLoanForm(emptyLoanForm);
      await refresh();
    } catch (e: any) {
      setError(e.message);
    }
  }

  async function handleCreateType(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      await createLoanType(typeForm);
      setTypeForm(emptyTypeForm);
      await refresh();
    } catch (e: any) {
      setError(e.message);
    }
  }

  async function handleToggleTypeActive(type: LoanType) {
    try {
      await updateLoanType(type.id, { is_active: !type.is_active });
      await refresh();
    } catch (e: any) {
      setError(e.message);
    }
  }

  async function handleToggleOpenForApplication(type: LoanType) {
    try {
      await updateLoanType(type.id, { open_for_application: !type.open_for_application });
      await refresh();
    } catch (e: any) {
      setError(e.message);
    }
  }

  async function handleMarkRepaid(loan: Loan) {
    const amount = prompt(
      `Record a repayment for ${loan.member_name} (balance: ${loan.balance})`
    );
    if (!amount) return;
    const parsed = parseFloat(amount);
    if (isNaN(parsed)) return;
    try {
      const newAmountRepaid = parseFloat(loan.amount_repaid) + parsed;
      await updateLoan(loan.id, { amount_repaid: newAmountRepaid });
      await refresh();
    } catch (e: any) {
      setError(e.message);
    }
  }

  async function handleDelete(id: string) {
    if (!confirm("Delete this loan record?")) return;
    try {
      await deleteLoan(id);
      await refresh();
    } catch (e: any) {
      setError(e.message);
    }
  }

  const selectedType = loanTypes.find((t) => t.id === loanForm.loan_type_id);
  const previewInterest =
    selectedType && loanForm.principal
      ? loanForm.principal * parseFloat(selectedType.interest_rate)
      : 0;
  const previewFlatCharge = selectedType ? parseFloat(selectedType.flat_charge) : 0;
  const previewTotal = loanForm.principal + previewInterest + previewFlatCharge;
  const previewInstallment = selectedType
    ? previewTotal / selectedType.tenure_months
    : 0;

  if (authLoading) return <main style={{ padding: 32 }}>Loading...</main>;

  return (
    <main style={{ padding: 32, maxWidth: 1100, margin: "0 auto" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <h1>Loans</h1>
        <button onClick={logout}>Log out</button>
      </div>

      {error && <p style={{ color: "crimson", fontWeight: 600 }}>Error: {error}</p>}

      <section style={{ marginBottom: 16 }}>
        <button onClick={() => setShowTypeManager(!showTypeManager)}>
          {showTypeManager ? "Hide" : "Manage"} loan types
        </button>
      </section>

      {showTypeManager && (
        <section
          style={{
            border: "1px solid #ddd",
            borderRadius: 8,
            padding: 16,
            marginBottom: 24,
          }}
        >
          <h2>Loan types</h2>
          <table style={{ width: "100%", borderCollapse: "collapse", marginBottom: 16 }}>
            <thead>
              <tr style={{ textAlign: "left", borderBottom: "2px solid #333" }}>
                <th>Name</th>
                <th>Rate</th>
                <th>Tenure (months)</th>
                <th>Flat charge</th>
                <th>Active</th>
                <th>Open for application</th>
              </tr>
            </thead>
            <tbody>
              {loanTypes.map((t) => (
                <tr key={t.id} style={{ borderBottom: "1px solid #eee" }}>
                  <td>{t.name}</td>
                  <td>{(parseFloat(t.interest_rate) * 100).toFixed(2)}%</td>
                  <td>{t.tenure_months}</td>
                  <td>{parseFloat(t.flat_charge) > 0 ? t.flat_charge : "—"}</td>
                  <td>
                    <button onClick={() => handleToggleTypeActive(t)}>
                      {t.is_active ? "Deactivate" : "Activate"}
                    </button>
                  </td>
                  <td>
                    <button onClick={() => handleToggleOpenForApplication(t)}>
                      {t.open_for_application ? "Close to members" : "Open to members"}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          <h3>Add loan type</h3>
          <form
            onSubmit={handleCreateType}
            style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}
          >
            <input
              required
              placeholder="Name (e.g. Capital Loan)"
              value={typeForm.name}
              onChange={(e) => setTypeForm({ ...typeForm, name: e.target.value })}
            />
            <input
              required
              type="number"
              step="0.0001"
              placeholder="Interest rate (e.g. 0.15 for 15%)"
              value={typeForm.interest_rate}
              onChange={(e) =>
                setTypeForm({ ...typeForm, interest_rate: parseFloat(e.target.value) })
              }
            />
            <input
              required
              type="number"
              placeholder="Tenure (months)"
              value={typeForm.tenure_months}
              onChange={(e) =>
                setTypeForm({ ...typeForm, tenure_months: parseInt(e.target.value) })
              }
            />
            <input
              type="number"
              step="0.01"
              placeholder="Flat charge (optional, e.g. 500)"
              value={typeForm.flat_charge}
              onChange={(e) =>
                setTypeForm({ ...typeForm, flat_charge: parseFloat(e.target.value) || 0 })
              }
            />
            <div style={{ gridColumn: "1 / -1" }}>
              <button type="submit">Add loan type</button>
            </div>
          </form>
        </section>
      )}

      <section
        style={{
          border: "1px solid #ddd",
          borderRadius: 8,
          padding: 16,
          marginBottom: 24,
        }}
      >
        <h2>Disburse a loan</h2>
        <form
          onSubmit={handleDisburse}
          style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}
        >
          <select
            required
            value={loanForm.member_id}
            onChange={(e) => setLoanForm({ ...loanForm, member_id: e.target.value })}
          >
            <option value="">Select member</option>
            {members.map((m) => (
              <option key={m.id} value={m.id}>
                {m.name} ({m.psn})
              </option>
            ))}
          </select>

          <select
            required
            value={loanForm.loan_type_id}
            onChange={(e) => setLoanForm({ ...loanForm, loan_type_id: e.target.value })}
          >
            <option value="">Select loan type</option>
            {loanTypes
              .filter((t) => t.is_active)
              .map((t) => (
                <option key={t.id} value={t.id}>
                  {t.name} ({(parseFloat(t.interest_rate) * 100).toFixed(1)}%,{" "}
                  {t.tenure_months}mo)
                </option>
              ))}
          </select>

          <input
            required
            type="number"
            step="0.01"
            placeholder="Principal amount"
            value={loanForm.principal || ""}
            onChange={(e) =>
              setLoanForm({ ...loanForm, principal: parseFloat(e.target.value) || 0 })
            }
          />

          <input
            required
            type="date"
            value={loanForm.disbursement_date}
            onChange={(e) =>
              setLoanForm({ ...loanForm, disbursement_date: e.target.value })
            }
          />

          <input
            placeholder="Notes (optional)"
            value={loanForm.notes}
            onChange={(e) => setLoanForm({ ...loanForm, notes: e.target.value })}
            style={{ gridColumn: "1 / -1" }}
          />

          {selectedType && loanForm.principal > 0 && (
            <div
              style={{
                gridColumn: "1 / -1",
                background: "#f6f6f6",
                padding: 8,
                borderRadius: 6,
                fontSize: 14,
              }}
            >
              Interest: {previewInterest.toFixed(2)}
              {previewFlatCharge > 0 && ` · Flat charge: ${previewFlatCharge.toFixed(2)}`}
              {" "}· Total repayable: {previewTotal.toFixed(2)} · Monthly installment:{" "}
              {previewInstallment.toFixed(2)}
            </div>
          )}

          <div style={{ gridColumn: "1 / -1" }}>
            <button type="submit">Disburse loan</button>
          </div>
        </form>
      </section>

      <section>
        <h2>All loans</h2>
        {loading ? (
          <p>Loading...</p>
        ) : (
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr style={{ textAlign: "left", borderBottom: "2px solid #333" }}>
                <th>Member</th>
                <th>Type</th>
                <th>Principal</th>
                <th>Balance</th>
                <th>Status</th>
                <th>Disbursed</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {loans.map((loan) => (
                <tr key={loan.id} style={{ borderBottom: "1px solid #eee" }}>
                  <td>
                    {loan.member_name} ({loan.member_psn})
                  </td>
                  <td>{loan.loan_type_name}</td>
                  <td>{loan.principal}</td>
                  <td>{loan.balance}</td>
                  <td>{loan.status}</td>
                  <td>{loan.disbursement_date}</td>
                  <td>
                    <button onClick={() => handleMarkRepaid(loan)}>
                      Record repayment
                    </button>{" "}
                    <button onClick={() => handleDelete(loan.id)}>Delete</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </main>
  );
}
