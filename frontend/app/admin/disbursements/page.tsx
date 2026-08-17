"use client";

import { useEffect, useState } from "react";
import { useAuth } from "../../../lib/useAuth";
import {
  listLoanApplications,
  listLoanTypes,
  listLoans,
  disburseApplication,
  LoanApplication,
  LoanType,
  Loan,
} from "../../../lib/api";

export default function AdminDisbursementsPage() {
  const { loading: authLoading, logout } = useAuth({
    requireAuth: true,
    requirePasswordChanged: true,
    requireRole: "admin",
  });

  const [applications, setApplications] = useState<LoanApplication[]>([]);
  const [loanTypes, setLoanTypes] = useState<LoanType[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const [filterLoanTypeId, setFilterLoanTypeId] = useState("");
  const [filterFrom, setFilterFrom] = useState("");
  const [filterTo, setFilterTo] = useState("");

  const [disbursing, setDisbursing] = useState<LoanApplication | null>(null);
  const [memberActiveLoans, setMemberActiveLoans] = useState<Loan[]>([]);
  const [selectedLoanIds, setSelectedLoanIds] = useState<string[]>([]);
  const [deductAll, setDeductAll] = useState(false);

  async function refresh() {
    setLoading(true);
    setError(null);
    try {
      const [appsData, typesData] = await Promise.all([
        listLoanApplications({
          undisbursed_only: true,
          loan_type_id: filterLoanTypeId || undefined,
        }),
        listLoanTypes(),
      ]);
      setApplications(appsData);
      setLoanTypes(typesData);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (!authLoading) refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [authLoading, filterLoanTypeId]);

  const filteredApplications = applications.filter((a) => {
    if (!filterFrom && !filterTo) return true;
    const reviewed = a.reviewed_at ? a.reviewed_at.slice(0, 10) : null;
    if (!reviewed) return true;
    if (filterFrom && reviewed < filterFrom) return false;
    if (filterTo && reviewed > filterTo) return false;
    return true;
  });

  async function openDisburseDialog(app: LoanApplication) {
    setError(null);
    setDisbursing(app);
    setSelectedLoanIds([]);
    setDeductAll(false);
    try {
      const loans = await listLoans({ member_id: app.member_id, status: "active" });
      setMemberActiveLoans(loans);
    } catch (e: any) {
      setError(e.message);
    }
  }

  function toggleLoanSelected(id: string) {
    setSelectedLoanIds((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]
    );
  }

  async function confirmDisburse() {
    if (!disbursing) return;
    setError(null);
    setSuccess(null);
    try {
      await disburseApplication(
        disbursing.id,
        deductAll ? undefined : selectedLoanIds.length > 0 ? selectedLoanIds : undefined,
        deductAll
      );
      setSuccess(`Disbursed ${disbursing.member_name}'s loan.`);
      setDisbursing(null);
      await refresh();
    } catch (e: any) {
      setError(e.message);
    }
  }

  if (authLoading || loading) return <main style={{ padding: 32 }}>Loading...</main>;

  return (
    <main style={{ padding: 32, maxWidth: 1100, margin: "0 auto" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <h1>Disburse Loans</h1>
        <button onClick={logout}>Log out</button>
      </div>
      <p style={{ color: "#555" }}>
        Approved loans awaiting disbursement. Disbursing sets the disbursement date to the 1st of
        this month, creates the active loan, and emails the member the full details.
      </p>

      {error && <p style={{ color: "crimson", fontWeight: 600 }}>{error}</p>}
      {success && <p style={{ color: "green", fontWeight: 600 }}>{success}</p>}

      <section style={{ marginBottom: 16, display: "flex", gap: 8, flexWrap: "wrap" }}>
        <select value={filterLoanTypeId} onChange={(e) => setFilterLoanTypeId(e.target.value)}>
          <option value="">All loan types</option>
          {loanTypes.map((t) => (
            <option key={t.id} value={t.id}>
              {t.name}
            </option>
          ))}
        </select>
        <label>
          Approved from:{" "}
          <input type="date" value={filterFrom} onChange={(e) => setFilterFrom(e.target.value)} />
        </label>
        <label>
          to:{" "}
          <input type="date" value={filterTo} onChange={(e) => setFilterTo(e.target.value)} />
        </label>
      </section>

      {filteredApplications.length === 0 ? (
        <p>No approved loans are currently waiting to be disbursed.</p>
      ) : (
        <table style={{ width: "100%", borderCollapse: "collapse", marginBottom: 24 }}>
          <thead>
            <tr style={{ textAlign: "left", borderBottom: "2px solid #333" }}>
              <th>Member</th>
              <th>Loan type</th>
              <th>Approved amount</th>
              <th>Tenure</th>
              <th>Preferred date</th>
              <th>Account</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {filteredApplications.map((a) => (
              <tr key={a.id} style={{ borderBottom: "1px solid #eee" }}>
                <td>
                  {a.member_name} ({a.member_psn})
                </td>
                <td>{a.loan_type_name}</td>
                <td>{a.approved_amount}</td>
                <td>{a.approved_tenure_months}mo</td>
                <td>{a.preferred_disbursement_date || "—"}</td>
                <td>
                  {a.use_default_account
                    ? "Default"
                    : `${a.alternate_bank_name} / ${a.alternate_account_name}`}
                </td>
                <td>
                  <button onClick={() => openDisburseDialog(a)}>Disburse</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {disbursing && (
        <section
          style={{
            border: "1px solid #ddd",
            borderRadius: 8,
            padding: 16,
          }}
        >
          <h2>
            Disburse {disbursing.member_name}'s {disbursing.loan_type_name} —{" "}
            {disbursing.approved_amount}
          </h2>

          {memberActiveLoans.length > 0 ? (
            <>
              <p style={{ color: "#555" }}>
                This member has {memberActiveLoans.length} active loan(s). You can fully close out
                some or all of them against this disbursement (they'll be marked repaid and
                completed; the amount deducted reduces what the member actually receives). No
                partial deduction — selected loans always close out completely.
              </p>
              <label>
                <input
                  type="checkbox"
                  checked={deductAll}
                  onChange={(e) => {
                    setDeductAll(e.target.checked);
                    if (e.target.checked) setSelectedLoanIds([]);
                  }}
                />{" "}
                Deduct all active loans
              </label>
              {!deductAll && (
                <table style={{ width: "100%", borderCollapse: "collapse", marginTop: 8 }}>
                  <thead>
                    <tr style={{ textAlign: "left" }}>
                      <th></th>
                      <th>Type</th>
                      <th>Balance</th>
                    </tr>
                  </thead>
                  <tbody>
                    {memberActiveLoans.map((loan) => (
                      <tr key={loan.id}>
                        <td>
                          <input
                            type="checkbox"
                            checked={selectedLoanIds.includes(loan.id)}
                            onChange={() => toggleLoanSelected(loan.id)}
                          />
                        </td>
                        <td>{loan.loan_type_name}</td>
                        <td>{loan.balance}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </>
          ) : (
            <p style={{ color: "#555" }}>This member has no other active loans.</p>
          )}

          <div style={{ marginTop: 16 }}>
            <button onClick={confirmDisburse}>Confirm disburse</button>{" "}
            <button onClick={() => setDisbursing(null)}>Cancel</button>
          </div>
        </section>
      )}
    </main>
  );
}
