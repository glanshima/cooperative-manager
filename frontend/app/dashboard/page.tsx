"use client";

import { useEffect, useState, Fragment } from "react";
import { useAuth } from "../../lib/useAuth";
import {
  listLoanApplications,
  submitLoanApplication,
  listLoanTypes,
  listLoans,
  getMyMemberRecord,
  getSettings,
  fileToBase64,
  submitRepayment,
  LoanApplication,
  LoanType,
  Loan,
  Member,
  Settings,
} from "../../lib/api";

const emptyForm = {
  loan_type_id: "",
  requested_amount: 0,
  requested_tenure_months: "" as number | "",
  preferred_disbursement_date: "",
  use_default_account: true,
  alternate_account_number: "",
  member_notes: "",
  payment_reference: "",
};

export default function MemberDashboard() {
  const { user, loading: authLoading, logout } = useAuth({
    requireAuth: true,
    requirePasswordChanged: true,
    requireRole: "member",
  });

  const [member, setMember] = useState<Member | null>(null);
  const [applications, setApplications] = useState<LoanApplication[]>([]);
  const [loans, setLoans] = useState<Loan[]>([]);
  const [loanTypes, setLoanTypes] = useState<LoanType[]>([]);
  const [settings, setSettings] = useState<Settings | null>(null);

  const [form, setForm] = useState(emptyForm);
  const [receiptFile, setReceiptFile] = useState<File | null>(null);
  const [showApplyForm, setShowApplyForm] = useState(false);

  const [servicingLoanId, setServicingLoanId] = useState<string | null>(null);
  const [repayAmount, setRepayAmount] = useState(0);
  const [repayReference, setRepayReference] = useState("");
  const [repayReceiptFile, setRepayReceiptFile] = useState<File | null>(null);

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  async function refresh() {
    setLoading(true);
    setError(null);
    try {
      const [memberData, appsData, loansData, typesData, settingsData] = await Promise.all([
        getMyMemberRecord(),
        listLoanApplications(),
        listLoans(),
        listLoanTypes(),
        getSettings(),
      ]);
      setMember(memberData);
      setApplications(appsData);
      setLoans(loansData);
      setLoanTypes(typesData);
      setSettings(settingsData);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (!authLoading && user) refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [authLoading, user]);

  async function handleSubmitApplication(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSuccess(null);

    if (!receiptFile) {
      setError("Please attach your payment receipt.");
      return;
    }
    if (!form.use_default_account && !form.alternate_account_number) {
      setError("Please provide an alternate account number, or use your default account.");
      return;
    }

    try {
      const base64 = await fileToBase64(receiptFile);
      await submitLoanApplication({
        loan_type_id: form.loan_type_id,
        requested_amount: form.requested_amount,
        requested_tenure_months: form.requested_tenure_months || undefined,
        preferred_disbursement_date: form.preferred_disbursement_date || undefined,
        use_default_account: form.use_default_account,
        alternate_account_number: form.use_default_account
          ? undefined
          : form.alternate_account_number,
        member_notes: form.member_notes,
        payment_reference: form.payment_reference,
        receipt_image_base64: base64,
        receipt_content_type: receiptFile.type,
      });
      setSuccess("Application submitted. It will be reviewed once your payment is verified.");
      setForm(emptyForm);
      setReceiptFile(null);
      setShowApplyForm(false);
      await refresh();
    } catch (e: any) {
      setError(e.message);
    }
  }

  async function handleSubmitRepayment(e: React.FormEvent) {
    e.preventDefault();
    if (!servicingLoanId) return;
    setError(null);
    setSuccess(null);

    if (!repayReceiptFile) {
      setError("Please attach your payment receipt.");
      return;
    }

    try {
      const base64 = await fileToBase64(repayReceiptFile);
      await submitRepayment(servicingLoanId, {
        amount_claimed: repayAmount,
        payment_reference: repayReference,
        receipt_image_base64: base64,
        receipt_content_type: repayReceiptFile.type,
      });
      setSuccess("Repayment submitted for verification.");
      setServicingLoanId(null);
      setRepayAmount(0);
      setRepayReference("");
      setRepayReceiptFile(null);
      await refresh();
    } catch (e: any) {
      setError(e.message);
    }
  }

  if (authLoading || loading) return <main style={{ padding: 32 }}>Loading...</main>;

  const applyableTypes = loanTypes.filter((t) => t.is_active && t.open_for_application);
  const selectedType = applyableTypes.find((t) => t.id === form.loan_type_id);

  const previewTenure = form.requested_tenure_months || selectedType?.tenure_months || 0;
  const previewInterest =
    selectedType && form.requested_amount
      ? form.requested_amount * parseFloat(selectedType.interest_rate)
      : 0;
  const previewFlatCharge = selectedType ? parseFloat(selectedType.flat_charge) : 0;
  const previewNetDisbursed = form.requested_amount - previewInterest;
  const previewTotalRepayable = form.requested_amount + previewFlatCharge;
  const previewInstallment = previewTenure > 0 ? previewTotalRepayable / previewTenure : 0;

  return (
    <main style={{ padding: 32, maxWidth: 900, margin: "0 auto" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <h1>My Dashboard</h1>
        <button onClick={logout}>Log out</button>
      </div>

      {member && (
        <p style={{ color: "#555" }}>
          {member.name} · PSN {member.psn}
        </p>
      )}

      {member?.loan_restricted && (
        <div
          style={{
            background: "#fff3cd",
            border: "1px solid #ffe69c",
            borderRadius: 6,
            padding: 12,
            marginBottom: 16,
          }}
        >
          Your account currently has a loan restriction noted by the cooperative.
          {settings?.loan_restriction_behavior === "block"
            ? " You won't be able to submit new applications until this is resolved."
            : " You can still apply, but this will be flagged for the reviewing admin."}
        </div>
      )}

      {error && <p style={{ color: "crimson", fontWeight: 600 }}>{error}</p>}
      {success && <p style={{ color: "green", fontWeight: 600 }}>{success}</p>}

      <section style={{ marginBottom: 24 }}>
        <button onClick={() => setShowApplyForm(!showApplyForm)}>
          {showApplyForm ? "Cancel" : "Apply for a loan"}
        </button>
      </section>

      {showApplyForm && (
        <section
          style={{
            border: "1px solid #ddd",
            borderRadius: 8,
            padding: 16,
            marginBottom: 24,
          }}
        >
          <h2>New loan application</h2>
          <p style={{ color: "#555" }}>
            A loan-form fee of <strong>{settings?.loan_form_fee}</strong> must be paid by bank
            transfer before your application can be reviewed. Enter your transfer reference and
            attach a photo/scan of the receipt below.
          </p>

          <form onSubmit={handleSubmitApplication} style={{ display: "grid", gap: 10 }}>
            <select
              required
              value={form.loan_type_id}
              onChange={(e) => setForm({ ...form, loan_type_id: e.target.value })}
            >
              <option value="">Select loan type</option>
              {applyableTypes.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.name} ({(parseFloat(t.interest_rate) * 100).toFixed(1)}%, {t.tenure_months}mo)
                </option>
              ))}
            </select>

            {selectedType?.description && (
              <p style={{ fontSize: 13, color: "#666", margin: 0 }}>{selectedType.description}</p>
            )}

            <input
              required
              type="number"
              step="0.01"
              placeholder="Amount requested"
              value={form.requested_amount || ""}
              onChange={(e) =>
                setForm({ ...form, requested_amount: parseFloat(e.target.value) || 0 })
              }
            />

            <label>
              Requested tenure in months (optional — leave blank to use the default; can only be
              shorter than or equal to the default):
              <input
                type="number"
                placeholder="e.g. 12"
                value={form.requested_tenure_months}
                onChange={(e) =>
                  setForm({
                    ...form,
                    requested_tenure_months: e.target.value ? parseInt(e.target.value) : "",
                  })
                }
              />
            </label>

            <label>
              Preferred disbursement date (a preference only — actual disbursement timing is set
              by the cooperative):
              <input
                type="date"
                value={form.preferred_disbursement_date}
                onChange={(e) => setForm({ ...form, preferred_disbursement_date: e.target.value })}
              />
            </label>

            {selectedType && form.requested_amount > 0 && (
              <div
                style={{
                  background: "#f6f6f6",
                  padding: 10,
                  borderRadius: 6,
                  fontSize: 14,
                }}
              >
                <strong>Estimated terms</strong> (final terms are set by the cooperative at
                approval, and may differ):
                <div>Interest (deducted at source): {previewInterest.toFixed(2)}</div>
                <div>Amount you would receive: {previewNetDisbursed.toFixed(2)}</div>
                {previewFlatCharge > 0 && <div>Flat charge: {previewFlatCharge.toFixed(2)}</div>}
                <div>Total repayable: {previewTotalRepayable.toFixed(2)}</div>
                <div>
                  Monthly installment ({previewTenure} months): {previewInstallment.toFixed(2)}
                </div>
              </div>
            )}

            <label>
              <input
                type="checkbox"
                checked={form.use_default_account}
                onChange={(e) => setForm({ ...form, use_default_account: e.target.checked })}
              />{" "}
              Send funds to my account on file
              {member?.account_number ? ` (${member.account_number})` : ""}
            </label>
            {!form.use_default_account && (
              <input
                required
                placeholder="Alternate account number for this loan only"
                value={form.alternate_account_number}
                onChange={(e) => setForm({ ...form, alternate_account_number: e.target.value })}
              />
            )}

            <textarea
              placeholder="Notes (optional) - e.g. reason for the loan"
              value={form.member_notes}
              onChange={(e) => setForm({ ...form, member_notes: e.target.value })}
            />

            <input
              required
              placeholder="Bank transfer reference number"
              value={form.payment_reference}
              onChange={(e) => setForm({ ...form, payment_reference: e.target.value })}
            />

            <label>
              Payment receipt (photo or PDF):
              <input
                required
                type="file"
                accept="image/*,application/pdf"
                onChange={(e) => setReceiptFile(e.target.files?.[0] || null)}
              />
            </label>

            <button type="submit">Submit application</button>
          </form>
        </section>
      )}

      <section style={{ marginBottom: 24 }}>
        <h2>My applications</h2>
        {applications.length === 0 ? (
          <p>No applications yet.</p>
        ) : (
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr style={{ textAlign: "left", borderBottom: "2px solid #333" }}>
                <th>Loan type</th>
                <th>Requested</th>
                <th>Tenure req.</th>
                <th>Approved</th>
                <th>Payment</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {applications.map((a) => {
                const rejectionNote =
                  a.payment_status === "rejected"
                    ? a.payment_rejection_reason
                    : a.status === "rejected"
                    ? a.admin_notes
                    : null;
                return (
                  <Fragment key={a.id}>
                    <tr style={{ borderBottom: rejectionNote ? "none" : "1px solid #eee" }}>
                      <td>{a.loan_type_name}</td>
                      <td>{a.requested_amount}</td>
                      <td>{a.requested_tenure_months ? `${a.requested_tenure_months}mo` : "default"}</td>
                      <td>{a.approved_amount || "—"}</td>
                      <td>{a.payment_status}</td>
                      <td>{a.status}</td>
                    </tr>
                    {rejectionNote && (
                      <tr style={{ borderBottom: "1px solid #eee" }}>
                        <td colSpan={6} style={{ color: "#b91c1c", fontSize: 13, paddingBottom: 8 }}>
                          Reason: {rejectionNote}
                        </td>
                      </tr>
                    )}
                  </Fragment>
                );
              })}
            </tbody>
          </table>
        )}
      </section>

      <section>
        <h2>My loans</h2>
        {loans.length === 0 ? (
          <p>No active or past loans.</p>
        ) : (
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr style={{ textAlign: "left", borderBottom: "2px solid #333" }}>
                <th>Type</th>
                <th>Principal</th>
                <th>Monthly installment</th>
                <th>Balance</th>
                <th>Status</th>
                <th>Expected end</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {loans.map((loan) => (
                <tr key={loan.id} style={{ borderBottom: "1px solid #eee" }}>
                  <td>{loan.loan_type_name}</td>
                  <td>{loan.principal}</td>
                  <td>{loan.monthly_installment}</td>
                  <td>{loan.balance}</td>
                  <td>{loan.status}</td>
                  <td>{loan.expected_end_date}</td>
                  <td>
                    {loan.status === "active" && (
                      <button
                        onClick={() => {
                          setServicingLoanId(loan.id);
                          setRepayAmount(parseFloat(loan.monthly_installment));
                        }}
                      >
                        Make a repayment
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}

        {servicingLoanId && (
          <section
            style={{
              border: "1px solid #ddd",
              borderRadius: 8,
              padding: 16,
              marginTop: 16,
            }}
          >
            <h3>Submit a repayment</h3>
            <form onSubmit={handleSubmitRepayment} style={{ display: "grid", gap: 10 }}>
              <input
                required
                type="number"
                step="0.01"
                placeholder="Amount paid"
                value={repayAmount || ""}
                onChange={(e) => setRepayAmount(parseFloat(e.target.value) || 0)}
              />
              <input
                required
                placeholder="Bank transfer reference number"
                value={repayReference}
                onChange={(e) => setRepayReference(e.target.value)}
              />
              <label>
                Payment receipt (photo or PDF):
                <input
                  required
                  type="file"
                  accept="image/*,application/pdf"
                  onChange={(e) => setRepayReceiptFile(e.target.files?.[0] || null)}
                />
              </label>
              <div>
                <button type="submit">Submit repayment</button>{" "}
                <button type="button" onClick={() => setServicingLoanId(null)}>
                  Cancel
                </button>
              </div>
            </form>
          </section>
        )}
      </section>
    </main>
  );
}
