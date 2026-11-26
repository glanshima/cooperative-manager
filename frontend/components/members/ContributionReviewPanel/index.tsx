"use client";

import { useState } from "react";
import type { ContributionChangeRequest } from "@/lib/api/contributions";
import { formatMoney } from "@/components/deductions/labels";
import { ConflictNotice } from "@/components/ui/ConflictMarker";
import ConfirmDialog from "@/components/ui/ConfirmDialog";

function money(value: string | null): string {
  return value ? `₦${formatMoney(value)}` : "Not set";
}

const STATUS_COLOR: Record<ContributionChangeRequest["status"], string> = {
  pending: "#8a6d00",
  approved: "green",
  rejected: "#a33",
};

export default function ContributionReviewPanel({
  requests,
  loading,
  error,
  onRefresh,
  onApprove,
  onReject,
}: {
  requests: ContributionChangeRequest[];
  loading: boolean;
  error?: string | null;
  onRefresh: () => void;
  onApprove: (id: string, reason: string) => Promise<boolean>;
  onReject: (id: string, reason: string) => Promise<boolean>;
}) {
  const [reasons, setReasons] = useState<Record<string, string>>({});
  const [busyId, setBusyId] = useState<string | null>(null);
  // A decision is not sent until it has been confirmed in a dialog.
  const [decision, setDecision] = useState<{ id: string; approve: boolean } | null>(null);

  // Pending decisions first; the backend already returns newest-first.
  const ordered = [...requests].sort((a, b) => {
    if (a.status === "pending" && b.status !== "pending") return -1;
    if (b.status === "pending" && a.status !== "pending") return 1;
    return 0;
  });

  const deciding = decision ? ordered.find((r) => r.id === decision.id) ?? null : null;

  async function runDecision() {
    if (!decision) return;
    const { id, approve } = decision;
    setBusyId(id);
    try {
      const ok = approve
        ? await onApprove(id, reasons[id] ?? "")
        : await onReject(id, reasons[id] ?? "");
      if (ok) {
        setDecision(null);
        setReasons((current) => ({ ...current, [id]: "" }));
      }
    } finally {
      setBusyId(null);
    }
  }

  return (
    <>
      <section style={{ border: "1px solid #ddd", borderRadius: 8, padding: 16, marginBottom: 24 }}>
        <div className="page-header">
          <h2 style={{ margin: 0 }}>Savings change requests</h2>
          <button onClick={onRefresh} disabled={loading}>
            {loading ? "Loading…" : "Refresh"}
          </button>
        </div>

        {ordered.length === 0 && (
          <p style={{ color: "#666", marginBottom: 0 }}>No savings change requests yet.</p>
        )}

        {ordered.map((r) => {
          const busy = busyId === r.id;
          const reason = reasons[r.id] ?? "";
          return (
            <div
              key={r.id}
              style={{ padding: 12, border: "1px solid #eee", borderRadius: 4, marginTop: 12 }}
            >
              <div style={{ display: "flex", flexWrap: "wrap", justifyContent: "space-between", alignItems: "baseline", gap: 8 }}>
                <strong>
                  {r.member_name ?? "Member"}
                  {r.member_psn ? ` · PSN ${r.member_psn?.replace("MCT-", "") ?? ""}` : ""}
                </strong>
                <span style={{ color: STATUS_COLOR[r.status], fontWeight: 600, fontSize: 13 }}>
                  {r.status}
                </span>
              </div>

              <p style={{ margin: "8px 0 0 0", fontSize: 14 }}>
                {money(r.current_amount)} → <strong>{money(r.requested_amount)}</strong>
              </p>
              {r.reason && <p style={{ margin: "6px 0 0 0", fontSize: 13, color: "#666" }}>{r.reason}</p>}
              <p style={{ margin: "6px 0 0 0", fontSize: 12, color: "#888" }}>
                Requested {new Date(r.created_at).toLocaleDateString()}
              </p>

              {r.status === "approved" && (
                <p style={{ margin: "6px 0 0 0", fontSize: 13, color: "green" }}>
                  Effective from {r.effective_from ?? "—"}
                  {r.review_reason ? ` · ${r.review_reason}` : ""}
                </p>
              )}
              {r.status === "rejected" && (
                <p style={{ margin: "6px 0 0 0", fontSize: 13, color: "#a33" }}>
                  Rejected {r.reviewed_at ? new Date(r.reviewed_at).toLocaleDateString() : ""}
                  {r.review_reason ? ` · ${r.review_reason}` : ""}
                </p>
              )}

              {r.status === "pending" && r.conflicted && <ConflictNotice entity="request" />}

              {r.status === "pending" && !r.conflicted && (
                <div style={{ marginTop: 10, display: "grid", gap: 8 }}>
                  <input
                    placeholder="Review reason (required to reject)"
                    value={reason}
                    disabled={busy}
                    onChange={(e) => setReasons((current) => ({ ...current, [r.id]: e.target.value }))}
                  />
                  <div className="toolbar">
                    <button onClick={() => setDecision({ id: r.id, approve: true })} disabled={busy}>
                      Approve
                    </button>
                    <button
                      onClick={() => setDecision({ id: r.id, approve: false })}
                      disabled={busy || !reason.trim()}
                    >
                      Reject
                    </button>
                  </div>
                  <p style={{ margin: 0, fontSize: 12, color: "#888" }}>
                    An approved amount applies from the first of next month, never retroactively.
                  </p>
                </div>
              )}
            </div>
          );
        })}
      </section>

      {decision && deciding && (
        <ConfirmDialog
          title={decision.approve ? "Approve savings change?" : "Reject savings change?"}
          message={
            decision.approve
              ? `Set ${deciding.member_name ?? "this member"}'s monthly savings to ${money(
                  deciding.requested_amount
                )}. The approved amount applies from the first of next month, never retroactively.`
              : `Reject ${deciding.member_name ?? "this member"}'s request to set their monthly savings to ${money(
                  deciding.requested_amount
                )}. Reason: ${reasons[deciding.id] ?? ""}`
          }
          confirmLabel={decision.approve ? "Approve" : "Reject"}
          busy={busyId !== null}
          error={error}
          onConfirm={runDecision}
          onCancel={() => setDecision(null)}
        />
      )}
    </>
  );
}
