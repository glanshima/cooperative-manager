"use client";

import { useState } from "react";
import type { ContributionChangeRequest } from "@/lib/api/contributions";
import { formatMoney } from "@/components/deductions/labels";
import { ConflictNotice } from "@/components/ui/ConflictMarker";

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
  onRefresh,
  onApprove,
  onReject,
}: {
  requests: ContributionChangeRequest[];
  loading: boolean;
  onRefresh: () => void;
  onApprove: (id: string, reason: string) => Promise<void>;
  onReject: (id: string, reason: string) => Promise<void>;
}) {
  const [reasons, setReasons] = useState<Record<string, string>>({});
  const [busyId, setBusyId] = useState<string | null>(null);

  // Pending decisions first; the backend already returns newest-first.
  const ordered = [...requests].sort((a, b) => {
    if (a.status === "pending" && b.status !== "pending") return -1;
    if (b.status === "pending" && a.status !== "pending") return 1;
    return 0;
  });

  async function act(id: string, approve: boolean) {
    setBusyId(id);
    try {
      if (approve) await onApprove(id, reasons[id] ?? "");
      else await onReject(id, reasons[id] ?? "");
      setReasons((current) => ({ ...current, [id]: "" }));
    } finally {
      setBusyId(null);
    }
  }

  return (
    <section style={{ border: "1px solid #ddd", borderRadius: 8, padding: 16, marginBottom: 24 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <h2 style={{ margin: 0 }}>Contribution change requests</h2>
        <button onClick={onRefresh} disabled={loading}>
          {loading ? "Loading…" : "Refresh"}
        </button>
      </div>

      {ordered.length === 0 && (
        <p style={{ color: "#666", marginBottom: 0 }}>No contribution change requests yet.</p>
      )}

      {ordered.map((r) => {
        const busy = busyId === r.id;
        const reason = reasons[r.id] ?? "";
        return (
          <div
            key={r.id}
            style={{ padding: 12, border: "1px solid #eee", borderRadius: 4, marginTop: 12 }}
          >
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
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
                <div style={{ display: "flex", gap: 8 }}>
                  <button onClick={() => act(r.id, true)} disabled={busy}>
                    Approve
                  </button>
                  <button onClick={() => act(r.id, false)} disabled={busy || !reason.trim()}>
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
  );
}