import ReceiptPreview from "@/components/ui/ReceiptPreview";
import { ConflictNotice } from "@/components/ui/ConflictMarker";
import type { LoanApplicationsPageModel } from "../hooks/useLoanApplicationsPage";

export default function ApplicationReviewPanel({
  review,
}: {
  review: LoanApplicationsPageModel["review"];
}) {
  const expanded = review.application;
  const form = review.form;
  if (!expanded) return null;

  // Opening an application is a read, which the conflict policy permits;
  // every decision below is a write, so the panel comes up without them.
  const readOnly = Boolean(expanded.conflicted);

  return (
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
        Reviewing: {expanded.member_name} ({expanded.member_psn?.replace("MCT-", "") ?? ""}) — {expanded.loan_type_name}
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
        <ReceiptPreview
          contentType={expanded.receipt_content_type}
          base64={expanded.receipt_image_base64}
        />
      </div>

      {readOnly && <ConflictNotice entity="application" />}

      {!readOnly && expanded.payment_status === "awaiting_verification" && (
        <div style={{ display: "grid", gap: 8 }}>
          <h3>Step 1: Verify payment</h3>
          <input
            placeholder="Rejection reason (if rejecting)"
            value={form.rejectionReason}
            onChange={(e) => form.setRejectionReason(e.target.value)}
          />
          <div>
            <button onClick={() => review.onVerifyPayment(true)}>Verify payment</button>{" "}
            <button onClick={() => review.onVerifyPayment(false)}>Reject payment</button>
          </div>
        </div>
      )}

      {!readOnly && expanded.payment_status === "verified" && expanded.status === "pending" && (
        <div style={{ display: "grid", gap: 8 }}>
          <h3>Step 2: Loan decision</h3>
          <input
            type="number"
            step="0.01"
            placeholder="Approved amount"
            value={form.approvedAmount}
            onChange={(e) => form.setApprovedAmount(e.target.value)}
          />
          <input
            type="number"
            placeholder="Approved tenure (months)"
            value={form.approvedTenureMonths}
            onChange={(e) => form.setApprovedTenureMonths(e.target.value)}
          />
          <input
            placeholder="Tenure decision reason (if different from what was requested)"
            value={form.tenureDecisionReason}
            onChange={(e) => form.setTenureDecisionReason(e.target.value)}
          />
          <textarea
            placeholder="Admin notes (sent to member if rejecting)"
            value={form.adminNotes}
            onChange={(e) => form.setAdminNotes(e.target.value)}
          />
          <label>
            <input
              type="checkbox"
              checked={form.canReapply}
              onChange={(e) => form.setCanReapply(e.target.checked)}
            />{" "}
            Member may reapply if rejected (uncheck only for genuine non-qualification, e.g.
            loan restriction — not for a fixable mistake like wrong amount)
          </label>
          <div>
            <button onClick={() => review.onDecide(true)}>Approve loan</button>{" "}
            <button onClick={() => review.onDecide(false)}>Reject loan</button>
          </div>
        </div>
      )}

      {!readOnly && expanded.status === "approved" && !expanded.resulting_loan_id && (
        <div style={{ display: "grid", gap: 8 }}>
          <h3>Step 3: Disburse</h3>
          <p style={{ color: "#555" }}>
            Approved: {expanded.approved_amount} over {expanded.approved_tenure_months} months.
            Disbursing will create the active loan, set the disbursement date to the 1st of
            this month, and email the member with full repayment details.
          </p>
          <div>
            <button onClick={() => review.onDisburse(expanded.id)}>Disburse now</button>
          </div>
        </div>
      )}

      <button onClick={review.close} style={{ marginTop: 12 }}>
        Close
      </button>
    </section>
  );
}
