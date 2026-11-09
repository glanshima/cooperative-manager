"use client";

import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { formatMoney } from "@/components/deductions/labels";
import type { Member } from "@/lib/api";
import {
  ContributionChangeRequest,
  createContributionChangeRequest,
  getMyContributionChangeRequests,
} from "@/lib/api/contributions";

const MINIMUM = 5000;

const cardStyle = {
  border: "1px solid #ddd",
  borderRadius: 8,
  padding: 16,
  marginTop: 24,
} as const;

export default function ContributionCard({ member }: { member: Member }) {
  const [requests, setRequests] = useState<ContributionChangeRequest[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [showRequestModal, setShowRequestModal] = useState(false);
  const [requestedAmount, setRequestedAmount] = useState("");
  const [reason, setReason] = useState("");

  async function loadRequests() {
    setLoading(true);
    try {
      setRequests(await getMyContributionChangeRequests());
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadRequests();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const isFinancial = member.status === "financial";
  const amount = member.monthly_contribution_amount;
  const pending = requests.find((r) => r.status === "pending");

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    const value = parseFloat(requestedAmount);
    if (!Number.isFinite(value) || value < MINIMUM) {
      setError(`The minimum monthly contribution is ₦${MINIMUM.toLocaleString()}.`);
      return;
    }
    if (!reason.trim()) {
      setError("Please give a reason for the change.");
      return;
    }
    setLoading(true);
    setError(null);
    setSuccess(null);
    try {
      await createContributionChangeRequest({ requested_amount: value, reason: reason.trim() });
      setSuccess("Change request submitted. An officer will review it.");
      setRequestedAmount("");
      setReason("");
      setShowRequestModal(false);
      await loadRequests();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  if (!isFinancial) {
    return (
      <section style={cardStyle}>
        <h2 style={{ marginTop: 0 }}>Monthly contribution</h2>
        <p style={{ color: "#666", marginBottom: 0 }}>
          Non-financial members don&apos;t have a monthly contribution. Anything you owe is
          recorded by an officer as a separate deduction.
        </p>
      </section>
    );
  }

  if (!amount) {
    return (
      <section style={cardStyle}>
        <h2 style={{ marginTop: 0 }}>Monthly contribution</h2>
        <p style={{ color: "#666", marginBottom: 0 }}>
          Your contribution amount is not yet set. Contact an officer to record it.
        </p>
      </section>
    );
  }

  return (
    <section style={cardStyle}>
      <h2 style={{ marginTop: 0 }}>Monthly contribution</h2>
      <div style={{ display: "flex", alignItems: "baseline", gap: 12, marginBottom: 12 }}>
        <span style={{ fontSize: 24, fontWeight: 600 }}>₦{formatMoney(amount)}</span>
        <span style={{ fontSize: 12, color: "#666" }}>per month</span>
      </div>

      <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
        <button onClick={() => setShowRequestModal(true)} disabled={loading || pending !== undefined}>
          {pending ? "Request pending" : "Request change"}
        </button>
        <button onClick={loadRequests} disabled={loading}>
          Refresh
        </button>
      </div>

      {pending && (
        <p style={{ color: "#8a6d00", marginTop: 8 }}>
          Your request to move to ₦{formatMoney(pending.requested_amount)} is pending review. An
          officer will approve or reject it; an approved amount applies from next month.
        </p>
      )}

      {error && !showRequestModal && <p style={{ color: "crimson", fontSize: 14 }}>{error}</p>}
      {success && <p style={{ color: "green", fontSize: 14 }}>{success}</p>}

      {requests.length > 0 && (
        <ul style={{ margin: "12px 0 0 0", padding: 0, listStyle: "none", fontSize: 13, color: "#555" }}>
          {requests.slice(0, 5).map((r) => (
            <li key={r.id} style={{ padding: "4px 0", borderTop: "1px solid #eee" }}>
              ₦{formatMoney(r.current_amount ?? "0")} → ₦{formatMoney(r.requested_amount)} ·{" "}
              <strong>{r.status}</strong>
              {r.status === "approved" && r.effective_from && ` · from ${r.effective_from}`}
              {r.status === "rejected" && r.review_reason && ` · ${r.review_reason}`}
            </li>
          ))}
        </ul>
      )}

      {showRequestModal && (
        <section
          style={{
            position: "fixed",
            inset: 0,
            background: "rgba(0,0,0,0.5)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            zIndex: 1000,
          }}
          onClick={(e) => {
            if (e.target === e.currentTarget) setShowRequestModal(false);
          }}
        >
          <section
            style={{ background: "white", borderRadius: 8, padding: 24, maxWidth: 400, width: "90%" }}
            onClick={(e) => e.stopPropagation()}
          >
            <h2 style={{ marginTop: 0 }}>Request contribution change</h2>
            <p style={{ color: "#666", marginBottom: 16 }}>
              Your current contribution is ₦{formatMoney(amount)}. Enter a new amount and a reason.
            </p>
            <form onSubmit={handleSubmit} style={{ display: "flex", flexDirection: "column", gap: 12 }}>
              <div>
                <label style={{ display: "block", fontSize: 12, color: "#555", marginBottom: 4 }}>
                  New amount
                </label>
                <input
                  type="number"
                  step="0.01"
                  min={MINIMUM}
                  required
                  value={requestedAmount}
                  onChange={(e) => setRequestedAmount(e.target.value)}
                  placeholder="e.g. 8000.00"
                  style={{ width: "100%" }}
                />
                <p style={{ fontSize: 12, color: "#b45309", marginTop: 4 }}>
                  Minimum is ₦{MINIMUM.toLocaleString()} per month.
                </p>
              </div>
              <div>
                <label style={{ display: "block", fontSize: 12, color: "#555", marginBottom: 4 }}>
                  Reason
                </label>
                <textarea
                  required
                  value={reason}
                  onChange={(e) => setReason(e.target.value)}
                  rows={3}
                  placeholder="e.g. Salary increase, need to increase savings"
                  style={{ width: "100%" }}
                />
              </div>
              {error && <p style={{ color: "crimson", fontSize: 14 }}>{error}</p>}
              <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
                <button type="submit" disabled={loading}>
                  Submit request
                </button>
                <button type="button" onClick={() => setShowRequestModal(false)} disabled={loading}>
                  Cancel
                </button>
              </div>
            </form>
          </section>
        </section>
      )}
    </section>
  );
}