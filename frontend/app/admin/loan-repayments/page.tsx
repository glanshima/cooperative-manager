"use client";

import { useEffect, useState } from "react";
import { useAuth } from "../../../lib/useAuth";
import {
  listAllRepayments,
  getRepayment,
  verifyRepayment,
  LoanRepayment,
  LoanRepaymentWithReceipt,
} from "../../../lib/api";

export default function AdminLoanRepaymentsPage() {
  const { loading: authLoading, logout } = useAuth({
    requireAuth: true,
    requirePasswordChanged: true,
    requireRole: "admin",
  });

  const [repayments, setRepayments] = useState<LoanRepayment[]>([]);
  const [expanded, setExpanded] = useState<LoanRepaymentWithReceipt | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [rejectionReason, setRejectionReason] = useState("");

  async function refresh() {
    setLoading(true);
    setError(null);
    try {
      setRepayments(await listAllRepayments());
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
      setExpanded(await getRepayment(id));
      setRejectionReason("");
    } catch (e: any) {
      setError(e.message);
    }
  }

  async function handleVerify(approved: boolean) {
    if (!expanded) return;
    setError(null);
    try {
      await verifyRepayment(expanded.id, approved, approved ? undefined : rejectionReason);
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
        <h1>Loan Repayments</h1>
        <button onClick={logout}>Log out</button>
      </div>

      {error && <p style={{ color: "crimson", fontWeight: 600 }}>{error}</p>}

      <table style={{ width: "100%", borderCollapse: "collapse", marginBottom: 24 }}>
        <thead>
          <tr style={{ textAlign: "left", borderBottom: "2px solid #333" }}>
            <th>Amount claimed</th>
            <th>Reference</th>
            <th>Status</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {repayments.map((r) => (
            <tr key={r.id} style={{ borderBottom: "1px solid #eee" }}>
              <td>{r.amount_claimed}</td>
              <td>{r.payment_reference}</td>
              <td>{r.status}</td>
              <td>
                <button onClick={() => handleExpand(r.id)}>Review</button>
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
          }}
        >
          <h2>Reviewing repayment of {expanded.amount_claimed}</h2>
          <p>Payment reference: {expanded.payment_reference}</p>

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

          {expanded.status === "awaiting_verification" && (
            <div style={{ display: "grid", gap: 8 }}>
              <input
                placeholder="Rejection reason (if rejecting)"
                value={rejectionReason}
                onChange={(e) => setRejectionReason(e.target.value)}
              />
              <div>
                <button onClick={() => handleVerify(true)}>Verify repayment</button>{" "}
                <button onClick={() => handleVerify(false)}>Reject repayment</button>
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
