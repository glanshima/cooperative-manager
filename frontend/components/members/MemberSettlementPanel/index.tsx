"use client";

import { useEffect, useState } from "react";
import type { FormEvent } from "react";

import StatusMessage from "@/components/ui/StatusMessage";
import { formatMoney } from "@/components/deductions/labels";
import {
  Member,
  MemberSettlementPreview,
  SettlementPaymentMethod,
  getMemberSettlement,
  markSettlementPaid,
  settleMemberExit,
} from "@/lib/api";

import { describeError } from "../utils";

function todayIso(): string {
  return new Date().toISOString().slice(0, 10);
}

function money(value?: string | null): string {
  return value ? `₦${formatMoney(value)}` : "—";
}

/**
 * What the office's books say about this member's exit: savings available,
 * loans still owed, and -- once settled -- exactly what was offset, what
 * was paid out, and whether that payout has changed hands.
 *
 * Settlement is a second, deliberate step after the exit is recorded, so
 * the panel asks for it explicitly rather than folding it into "Record
 * exit". Members who have not exited get no panel at all.
 */
export default function MemberSettlementPanel({
  member,
  canView,
  canSettle,
}: {
  member: Member;
  canView: boolean;
  canSettle: boolean;
}) {
  const isExited = Boolean(member.membership_exit_date);

  const [preview, setPreview] = useState<MemberSettlementPreview | null>(null);
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [settleOpen, setSettleOpen] = useState(false);
  const [settledOn, setSettledOn] = useState(todayIso());
  const [settleNote, setSettleNote] = useState("");

  const [paidOpen, setPaidOpen] = useState(false);
  const [paidOn, setPaidOn] = useState(todayIso());
  const [paidFrom, setPaidFrom] = useState<SettlementPaymentMethod>("bank");
  const [reference, setReference] = useState("");
  const [paidNote, setPaidNote] = useState("");

  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  async function load() {
    if (!isExited || !canView) return;
    setLoading(true);
    setLoadError(null);
    try {
      setPreview(await getMemberSettlement(member.id));
    } catch (e: unknown) {
      setLoadError(describeError(e));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    setPreview(null);
    setSettleOpen(false);
    setPaidOpen(false);
    setActionError(null);
    setSettledOn(todayIso());
    setPaidOn(todayIso());
    setPaidFrom("bank");
    setReference("");
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [member.id, isExited, canView]);

  if (!isExited || !canView) return null;

  const settlement = preview?.settlement ?? null;
  const canSettleNow =
    canSettle &&
    preview !== null &&
    !settlement &&
    (Number(preview.savings_balance) > 0 || preview.active_loan_count > 0);

  async function submitSettle(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setActionError(null);
    try {
      await settleMemberExit(member.id, {
        settled_on: settledOn || undefined,
        note: settleNote.trim() || undefined,
      });
      setSettleOpen(false);
      setSettleNote("");
      await load();
    } catch (err: unknown) {
      setActionError(describeError(err));
    } finally {
      setBusy(false);
    }
  }

  async function submitPaid(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setActionError(null);
    try {
      await markSettlementPaid(member.id, {
        paid_on: paidOn || undefined,
        reference: reference.trim(),
        paid_from: paidFrom,
        note: paidNote.trim() || undefined,
      });
      setPaidOpen(false);
      setReference("");
      setPaidNote("");
      setPaidFrom("bank");
      await load();
    } catch (err: unknown) {
      setActionError(describeError(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section aria-label="Exit settlement" style={{ marginTop: 20 }}>
      <h3 style={{ margin: "0 0 8px", fontSize: 15 }}>Exit settlement</h3>

      {loading && <p style={{ color: "var(--text-muted)" }}>Loading settlement…</p>}
      {loadError && <StatusMessage tone="error">Error: {loadError}</StatusMessage>}
      {actionError && (
        <StatusMessage tone="error" onDismiss={() => setActionError(null)}>
          {actionError}
        </StatusMessage>
      )}

      {preview && !settlement && (
        <>
          <dl className="detail-grid">
            <div>
              <dt>Savings available</dt>
              <dd>{money(preview.savings_balance)}</dd>
            </div>
            <div>
              <dt>Loans outstanding</dt>
              <dd>
                {money(preview.active_loan_outstanding)}
                {preview.active_loan_count > 0 &&
                  ` (${preview.active_loan_count} loan${preview.active_loan_count === 1 ? "" : "s"})`}
              </dd>
            </div>
          </dl>

          {!canSettleNow && (
            <p style={{ color: "var(--text-muted)", fontSize: 14 }}>
              {canSettle
                ? "There is nothing to settle: no savings and no loan balance."
                : "Only an officer with the savings settlement permission can settle this exit."}
            </p>
          )}

          {canSettleNow && !settleOpen && (
            <p style={{ marginTop: 12 }}>
              <button type="button" className="link-button" onClick={() => setSettleOpen(true)}>
                Settle exit
              </button>
            </p>
          )}

          {canSettleNow && settleOpen && (
            <form onSubmit={submitSettle} className="form-grid" style={{ marginTop: 12 }}>
              <label style={{ fontSize: 13, color: "var(--text-muted)" }}>
                Settlement date
                <input
                  type="date"
                  aria-label="Settlement date"
                  value={settledOn}
                  max={todayIso()}
                  onChange={(e) => setSettledOn(e.target.value)}
                  required
                />
              </label>
              <input
                aria-label="Settlement note"
                placeholder="Note (optional)"
                className="form-grid__full"
                value={settleNote}
                onChange={(e) => setSettleNote(e.target.value)}
              />
              <p className="form-grid__full" style={{ margin: 0, fontSize: 13, color: "var(--text-muted)" }}>
                Savings offset active loans oldest first; whatever remains is recorded as a payout
                the office owes the member.
              </p>
              <div className="form-grid__full toolbar">
                <button type="submit" disabled={busy}>
                  {busy ? "Settling…" : "Settle savings"}
                </button>
                <button type="button" disabled={busy} onClick={() => setSettleOpen(false)}>
                  Cancel
                </button>
              </div>
            </form>
          )}
        </>
      )}

      {settlement && (
        <>
          <dl className="detail-grid">
            <div>
              <dt>Settled on</dt>
              <dd>{settlement.settled_on}</dd>
            </div>
            <div>
              <dt>Savings at settlement</dt>
              <dd>{money(settlement.savings_balance)}</dd>
            </div>
            <div>
              <dt>Applied to loans</dt>
              <dd>{money(settlement.offset_total)}</dd>
            </div>
            <div>
              <dt>Payout</dt>
              <dd>{money(settlement.payout_amount)}</dd>
            </div>
            <div>
              <dt>Payout status</dt>
              <dd>{settlement.payout_status === "paid" ? "Paid" : "Pending"}</dd>
            </div>
            {settlement.payout_status === "paid" && (
              <>
                <div>
                  <dt>Paid on</dt>
                  <dd>{settlement.paid_on ?? "—"}</dd>
                </div>
                <div>
                  <dt>Reference</dt>
                  <dd>{settlement.paid_reference ?? "—"}</dd>
                </div>
                <div>
                  <dt>Paid from</dt>
                  <dd>{settlement.paid_from === "cash" ? "Cash" : settlement.paid_from === "bank" ? "Bank" : "—"}</dd>
                </div>
              </>
            )}
            {settlement.note && (
              <div className="detail-grid__full">
                <dt>Note</dt>
                <dd>{settlement.note}</dd>
              </div>
            )}
          </dl>

          {settlement.allocations.length > 0 && (
            <div style={{ marginTop: 12 }}>
              <p style={{ margin: "0 0 4px", fontSize: 12, textTransform: "uppercase", letterSpacing: "0.04em", color: "var(--text-muted)" }}>
                Savings applied to
              </p>
              <ul style={{ margin: 0, paddingLeft: 18, fontSize: 14 }}>
                {settlement.allocations.map((item) => (
                  <li key={item.loan_id}>
                    {item.loan_type_name || "Loan"} — {money(item.amount)}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {settlement.payout_status === "pending" && canSettle && (
            <div style={{ marginTop: 12 }}>
              {!paidOpen && (
                <p style={{ margin: 0 }}>
                  <button type="button" className="link-button" onClick={() => setPaidOpen(true)}>
                    Mark payout paid
                  </button>
                </p>
              )}
              {paidOpen && (
                <form onSubmit={submitPaid} className="form-grid">
                  <label style={{ fontSize: 13, color: "var(--text-muted)" }}>
                    Paid on
                    <input
                      type="date"
                      aria-label="Payout date"
                      value={paidOn}
                      min={settlement.settled_on}
                      max={todayIso()}
                      onChange={(e) => setPaidOn(e.target.value)}
                      required
                    />
                  </label>
                  <label style={{ fontSize: 13, color: "var(--text-muted)" }}>
                    Paid from
                    <select
                      aria-label="Paid from"
                      value={paidFrom}
                      onChange={(e) => setPaidFrom(e.target.value as SettlementPaymentMethod)}
                    >
                      <option value="bank">Bank</option>
                      <option value="cash">Cash</option>
                    </select>
                  </label>
                  <input
                    aria-label="Payment reference"
                    placeholder="Bank or cash reference *"
                    value={reference}
                    onChange={(e) => setReference(e.target.value)}
                    required
                  />
                  <input
                    aria-label="Payment note"
                    placeholder="Note (optional)"
                    className="form-grid__full"
                    value={paidNote}
                    onChange={(e) => setPaidNote(e.target.value)}
                  />
                  <div className="form-grid__full toolbar">
                    <button type="submit" disabled={busy || !reference.trim()}>
                      {busy ? "Recording…" : "Record payout"}
                    </button>
                    <button type="button" disabled={busy} onClick={() => setPaidOpen(false)}>
                      Cancel
                    </button>
                  </div>
                </form>
              )}
            </div>
          )}

          {settlement.payout_status === "pending" && !canSettle && (
            <p style={{ fontSize: 14, color: "var(--text-muted)" }}>
              The payout is waiting to be handed over. An officer with the savings settlement
              permission records it as paid.
            </p>
          )}
        </>
      )}
    </section>
  );
}
