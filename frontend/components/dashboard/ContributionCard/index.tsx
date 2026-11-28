"use client";

import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { formatMoney } from "@/components/deductions/labels";
import Modal from "@/components/ui/Modal";
import StatusMessage from "@/components/ui/StatusMessage";
import { getSettings, type Member } from "@/lib/api";
import {
  ContributionChangeRequest,
  createContributionChangeRequest,
  getMyContributionChangeRequests,
  getMySavings,
  MemberSavings,
} from "@/lib/api/contributions";

const cardStyle = {
  border: "1px solid #ddd",
  borderRadius: 8,
  padding: 16,
  marginTop: 24,
} as const;

export default function ContributionCard({ member }: { member: Member }) {
  const [requests, setRequests] = useState<ContributionChangeRequest[]>([]);
  const [savings, setSavings] = useState<MemberSavings | null>(null);
  // The cooperative's floor, as a setting; 0 means it sets none.
  const [minimum, setMinimum] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [requestHistoryError, setRequestHistoryError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [showRequestModal, setShowRequestModal] = useState(false);
  const [requestedAmount, setRequestedAmount] = useState("");
  const [reason, setReason] = useState("");

  async function loadRequests() {
    setLoading(true);
    setRequestHistoryError(null);
    try {
      // Settled, not all: a savings lookup failing must not hide the
      // member's own change-request history.
      const [requestResult, savingsResult, settingsResult] = await Promise.allSettled([
        getMyContributionChangeRequests(),
        getMySavings(),
        getSettings(),
      ]);
      if (requestResult.status === "fulfilled") {
        setRequests(requestResult.value);
      } else {
        setRequestHistoryError(
          "Could not load your request history. Refresh to check pending requests."
        );
      }
      if (savingsResult.status === "fulfilled") setSavings(savingsResult.value);
      if (settingsResult.status === "fulfilled") {
        setMinimum(Number(settingsResult.value.minimum_monthly_contribution));
      }
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

  // What payroll has actually remitted for this member, confirmed records
  // only -- the figure they can reconcile against their own payslips.
  const savingsSummary = savings ? (
    <p style={{ margin: "0 0 12px", fontSize: 14 }}>
      <strong style={{ fontSize: 20 }}>₦{formatMoney(savings.savings_balance)}</strong> saved so
      far
      {savings.months_contributed > 0 && (
        <span style={{ color: "#666" }}>
          {" "}
          · across {savings.months_contributed} month{savings.months_contributed === 1 ? "" : "s"}
        </span>
      )}
    </p>
  ) : null;

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    const value = parseFloat(requestedAmount);
    if (!Number.isFinite(value) || value <= 0) {
      setError("Enter the monthly amount you want to save.");
      return;
    }
    if (minimum > 0 && value < minimum) {
      setError(`The minimum monthly savings is ₦${minimum.toLocaleString()}.`);
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
        <h2 style={{ marginTop: 0 }}>Monthly savings</h2>
        {savingsSummary}
        <p style={{ color: "#666", marginBottom: 0 }}>
          Non-financial members don&apos;t have a monthly savings amount. Anything you owe is
          recorded by an officer as a separate deduction.
        </p>
      </section>
    );
  }

  return (
    <section style={cardStyle}>
      <h2 style={{ marginTop: 0 }}>Monthly savings</h2>
      {savingsSummary}
      <div style={{ display: "flex", alignItems: "baseline", gap: 12, marginBottom: 12 }}>
        {amount ? (
          <>
            <span style={{ fontSize: 24, fontWeight: 600 }}>₦{formatMoney(amount)}</span>
            <span style={{ fontSize: 12, color: "#666" }}>per month</span>
          </>
        ) : (
          <span style={{ fontSize: 20, fontWeight: 600, color: "#666" }}>Not yet set</span>
        )}
      </div>
      {!amount && (
        <p style={{ color: "#666", marginTop: 0 }}>
          You do not have a monthly savings amount yet. You can request an initial amount.
        </p>
      )}

      <div className="toolbar">
        <button onClick={() => setShowRequestModal(true)} disabled={loading || pending !== undefined}>
          {pending ? "Request pending" : amount ? "Request change" : "Request amount"}
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

      {requestHistoryError && (
        <StatusMessage
          tone="error"
          dismissLabel="Dismiss request history error"
          onDismiss={() => setRequestHistoryError(null)}
        >
          {requestHistoryError}
        </StatusMessage>
      )}
      {error && !showRequestModal && (
        <StatusMessage tone="error" dismissLabel="Dismiss savings error" onDismiss={() => setError(null)}>
          {error}
        </StatusMessage>
      )}
      {success && (
        <StatusMessage
          tone="success"
          dismissLabel="Dismiss success message"
          onDismiss={() => setSuccess(null)}
        >
          {success}
        </StatusMessage>
      )}

      {requests.length > 0 && (
        <ul style={{ margin: "12px 0 0 0", padding: 0, listStyle: "none", fontSize: 13, color: "#555" }}>
          {requests.slice(0, 5).map((r) => (
            <li key={r.id} style={{ padding: "4px 0", borderTop: "1px solid #eee" }}>
              {r.current_amount == null ? "Not set" : `₦${formatMoney(r.current_amount)}`} →{" "}
              {`₦${formatMoney(r.requested_amount)}`} · <strong>{r.status}</strong>
              {r.status === "approved" && r.effective_from && ` · from ${r.effective_from}`}
              {r.status === "rejected" && r.review_reason && ` · ${r.review_reason}`}
            </li>
          ))}
        </ul>
      )}

      {showRequestModal && (
        <Modal
          title="Request savings change"
          onClose={() => setShowRequestModal(false)}
          busy={loading}
          closeLabel="Close savings request"
          maxWidth={400}
        >
          <p style={{ color: "#666", marginBottom: 16 }}>
            {amount
              ? `Your current monthly savings is ₦${formatMoney(amount)}. Enter a new amount and a reason.`
              : "No monthly savings amount is set yet. Enter your initial amount and a reason."}
          </p>
          <form onSubmit={handleSubmit} style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            <div>
              <label style={{ display: "block", fontSize: 12, color: "#555", marginBottom: 4 }}>
                New amount
              </label>
              <input
                type="number"
                step="0.01"
                min={minimum > 0 ? minimum : 0}
                required
                value={requestedAmount}
                onChange={(e) => setRequestedAmount(e.target.value)}
                placeholder="e.g. 8000.00"
                style={{ width: "100%" }}
              />
              {minimum > 0 && (
                <p style={{ fontSize: 12, color: "#b45309", marginTop: 4 }}>
                  Minimum is ₦{minimum.toLocaleString()} per month.
                </p>
              )}
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
            <div className="toolbar" style={{ marginTop: 8 }}>
              <button type="submit" disabled={loading}>
                Submit request
              </button>
              <button type="button" onClick={() => setShowRequestModal(false)} disabled={loading}>
                Cancel
              </button>
            </div>
          </form>
        </Modal>
      )}
    </section>
  );
}