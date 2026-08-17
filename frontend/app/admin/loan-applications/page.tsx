"use client";

import { useEffect, useState } from "react";
import { useAuth } from "../../../lib/useAuth";
import {
  listLoanApplications,
  getLoanApplication,
  verifyPayment,
  decideApplication,
  disburseApplication,
  LoanApplication,
  LoanApplicationWithReceipt,
} from "../../../lib/api";

export default function AdminLoanApplicationsPage() {
  const { loading: authLoading, logout } = useAuth({
    requireAuth: true,
    requirePasswordChanged: true,
    requireRole: "admin",
  });

  const [applications, setApplications] = useState<LoanApplication[]>([]);
  const [expanded, setExpanded] = useState<LoanApplicationWithReceipt | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [approvedAmount, setApprovedAmount] = useState("");
  const [approvedTenureMonths, setApprovedTenureMonths] = useState("");
  const [tenureDecisionReason, setTenureDecisionReason] = useState("");
  const [adminNotes, setAdminNotes] = useState("");
  const [rejectionReason, setRejectionReason] = useState("");
  const [canReapply, setCanReapply] = useState(true);

  async function refresh() {
    setLoading(true);
    setError(null);
    try {
      setApplications(await listLoanApplications());
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

  async function handleExpand(id: string) {
    setError(null);
    try {
      const full = await getLoanApplication(id);
      setExpanded(full);
      setApprovedAmount(full.requested_amount);
      setApprovedTenureMonths(
        full.requested_tenure_months ? String(full.requested_tenure_months) : ""
      );
      setTenureDecisionReason("");
      setAdminNotes("");
      setRejectionReason("");
      setCanReapply(true);
    } catch (e: any) {
      setError(e.message);
    }
  }

  async function handleVerifyPayment(approved: boolean) {
    if (!expanded) return;
    setError(null);
    try {
      await verifyPayment(expanded.id, approved, approved ? undefined : rejectionReason);
      setExpanded(null);
      await refresh();
    } catch (e: any) {
      setError(e.message);
    }
  }

  async function handleDecide(approved: boolean) {
    if (!expanded) return;
    setError(null);
    try {
      await decideApplication(
        expanded.id,
        approved,
        approved ? parseFloat(approvedAmount) : undefined,
        approved ? parseInt(approvedTenureMonths) : undefined,
        tenureDecisionReason || undefined,
        adminNotes || undefined,
        canReapply
      );
      setExpanded(null);
      await refresh();
    } catch (e: any) {
      setError(e.message);
    }
  }

  async function handleDisburse(id: string) {
    if (!confirm("Disburse this loan now? This will move it to active and email the member.")) return;
    setError(null);
    try {
      await disburseApplication(id);
      setExpanded(null);
      await refresh();
    } catch (e: any) {
      setError(e.message);
    }
  }

  if (authLoading || loading) return <main style={{ padding: 32 }}>Loading...</main>;

  return (
    <main style={{ padding: 32, maxWidth: 1000, margin: "0 auto" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <h1>Loan Applications</h1>
        <button onClick={logout}>Log out</button>
      </div>

      {error && <p style={{ color: "crimson", fontWeight: 600 }}>{error}</p>}

      <table style={{ width: "100%", borderCollapse: "collapse", marginBottom: 24 }}>
        <thead>
          <tr style={{ textAlign: "left", borderBottom: "2px solid #333" }}>
            <th>Member</th>
            <th>Type</th>
            <th>Requested</th>
            <th>Payment</th>
            <th>Status</th>
            <th>Flag</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {applications.map((a) => (
            <tr key={a.id} style={{ borderBottom: "1px solid #eee" }}>
              <td>
                {a.member_name} ({a.member_psn})
              </td>
              <td>{a.loan_type_name}</td>
              <td>{a.requested_amount}</td>
              <td>{a.payment_status}</td>
              <td>{a.status}</td>
              <td>
                {a.was_restricted_at_submission && (
                  <span style={{ color: "#b45309", fontWeight: 600 }}>⚠ restricted</span>
                )}
              </td>
              <td>
                <button onClick={() => handleExpand(a.id)}>Review</button>{" "}
                {a.status === "approved" && !a.resulting_loan_id && (
                  <button onClick={() => handleDisburse(a.id)}>Disburse</button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      {expanded && (
        <section
          style={{
            border: "1px solid #ddd",
            borderRadius: 8,
            padding: 16,
            position: "sticky",
            bottom: 16,
            background: "#fff",
          }}
        >
          <h2>
            Reviewing: {expanded.member_name} ({expanded.member_psn}) — {expanded.loan_type_name}
          </h2>
          <p>
            Requested: {expanded.requested_amount} · Payment reference: {expanded.payment_reference}
          </p>
          <p style={{ color: "#555" }}>
            Requested tenure: {expanded.requested_tenure_months ? `${expanded.requested_tenure_months} months` : "default"}
            {" · "}
            Preferred disbursement date: {expanded.preferred_disbursement_date || "not specified"}
            {" · "}
            Account:{" "}
            {expanded.use_default_account
              ? "member's default account"
              : `alternate — ${expanded.alternate_bank_name}, ${expanded.alternate_account_name}, ${expanded.alternate_account_number}`}
          </p>

          {expanded.was_restricted_at_submission && (
            <p style={{ color: "#b45309", fontWeight: 600 }}>
              ⚠ This member was flagged as loan-restricted when they submitted this application.
              {expanded.restriction_reason_snapshot && ` Reason: ${expanded.restriction_reason_snapshot}`}
            </p>
          )}

          <div style={{ margin: "12px 0" }}>
            {expanded.receipt_content_type.startsWith("image/") ? (
              <img
                src={`data:${expanded.receipt_content_type};base64,${expanded.receipt_image_base64}`}
                alt="Payment receipt"
                style={{ maxWidth: "100%", maxHeight: 400, border: "1px solid #ccc" }}
              />
            ) : (
              <a
                href={`data:${expanded.receipt_content_type};base64,${expanded.receipt_image_base64}`}
                download="receipt"
              >
                Download receipt (PDF)
              </a>
            )}
          </div>

          {expanded.payment_status === "awaiting_verification" && (
            <div style={{ display: "grid", gap: 8 }}>
              <h3>Step 1: Verify payment</h3>
              <input
                placeholder="Rejection reason (if rejecting)"
                value={rejectionReason}
                onChange={(e) => setRejectionReason(e.target.value)}
              />
              <div>
                <button onClick={() => handleVerifyPayment(true)}>Verify payment</button>{" "}
                <button onClick={() => handleVerifyPayment(false)}>Reject payment</button>
              </div>
            </div>
          )}

          {expanded.payment_status === "verified" && expanded.status === "pending" && (
            <div style={{ display: "grid", gap: 8 }}>
              <h3>Step 2: Loan decision</h3>
              <input
                type="number"
                step="0.01"
                placeholder="Approved amount"
                value={approvedAmount}
                onChange={(e) => setApprovedAmount(e.target.value)}
              />
              <input
                type="number"
                placeholder="Approved tenure (months)"
                value={approvedTenureMonths}
                onChange={(e) => setApprovedTenureMonths(e.target.value)}
              />
              <input
                placeholder="Tenure decision reason (if different from what was requested)"
                value={tenureDecisionReason}
                onChange={(e) => setTenureDecisionReason(e.target.value)}
              />
              <textarea
                placeholder="Admin notes (sent to member if rejecting)"
                value={adminNotes}
                onChange={(e) => setAdminNotes(e.target.value)}
              />
              <label>
                <input
                  type="checkbox"
                  checked={canReapply}
                  onChange={(e) => setCanReapply(e.target.checked)}
                />{" "}
                Member may reapply if rejected (uncheck only for genuine non-qualification, e.g.
                loan restriction — not for a fixable mistake like wrong amount)
              </label>
              <div>
                <button onClick={() => handleDecide(true)}>Approve loan</button>{" "}
                <button onClick={() => handleDecide(false)}>Reject loan</button>
              </div>
            </div>
          )}

          {expanded.status === "approved" && !expanded.resulting_loan_id && (
            <div style={{ display: "grid", gap: 8 }}>
              <h3>Step 3: Disburse</h3>
              <p style={{ color: "#555" }}>
                Approved: {expanded.approved_amount} over {expanded.approved_tenure_months} months.
                Disbursing will create the active loan, set the disbursement date to the 1st of
                this month, and email the member with full repayment details.
              </p>
              <div>
                <button onClick={() => handleDisburse(expanded.id)}>Disburse now</button>
              </div>
            </div>
          )}

          <button onClick={() => setExpanded(null)} style={{ marginTop: 12 }}>
            Close
          </button>
        </section>
      )}
    </main>
  );
}
