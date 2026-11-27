import CloseButton from "@/components/ui/CloseButton";
import ReceiptPreview from "@/components/ui/ReceiptPreview";
import { ConflictNotice } from "@/components/ui/ConflictMarker";
import { formatMoney } from "@/components/deductions/labels";
import { INTEREST_MODE_LABELS } from "@/lib/loanMath";
import type { LoanApplicationsPageModel } from "../hooks/useLoanApplicationsPage";
import styles from "./ApplicationReviewPanel.module.css";

const PAYMENT_STATUS_LABELS = {
  awaiting_verification: "Awaiting verification",
  verified: "Verified",
  rejected: "Rejected",
} as const;

function money(value?: string | null) {
  return value ? `₦${formatMoney(value)}` : "—";
}

export default function ApplicationReviewPanel({
  review,
}: {
  review: LoanApplicationsPageModel["review"];
}) {
  const expanded = review.application;
  const form = review.form;
  if (!expanded) return null;

  const readOnly = Boolean(expanded.conflicted);
  const paymentComplete = expanded.payment_status === "verified";
  const decisionComplete =
    expanded.status === "approved" || (expanded.status === "rejected" && paymentComplete);
  const disbursementComplete = Boolean(expanded.resulting_loan_id);
  const currentStage = disbursementComplete || expanded.status === "approved"
    ? 3
    : paymentComplete
      ? 2
      : 1;
  const stopped = expanded.status === "rejected" || expanded.status === "cancelled";
  const stages = [
    {
      label: "Review and verify",
      detail: PAYMENT_STATUS_LABELS[expanded.payment_status],
      complete: paymentComplete,
    },
    {
      label: "Approve or reject",
      detail:
        expanded.status === "approved"
          ? "Approved"
          : expanded.status === "rejected"
            ? paymentComplete
              ? "Rejected"
              : "Not reached"
            : expanded.status === "cancelled"
              ? "Cancelled"
              : "Awaiting decision",
      complete: decisionComplete,
    },
    {
      label: "Disburse",
      detail: disbursementComplete
        ? "Disbursed"
        : expanded.status === "approved"
          ? "Awaiting disbursement"
          : stopped
            ? "Not applicable"
            : "Locked until approval",
      complete: disbursementComplete,
    },
  ];

  return (
    <section className={styles.panel} aria-label="Application review">
      <div className={styles.header}>
        <div>
          <p className={styles.eyebrow}>Application workflow</p>
          <h2>
            {expanded.member_name} ({expanded.member_psn?.replace("MCT-", "") ?? ""})
          </h2>
          <p className={styles.subtitle}>{expanded.loan_type_name}</p>
        </div>
        <CloseButton label="Close application review" onClick={review.close} />
      </div>

      <ol className={styles.stepper} aria-label="Application workflow stages">
        {stages.map((stage, index) => {
          const step = index + 1;
          const state = step === currentStage
            ? "current"
            : stage.complete
              ? "complete"
              : stopped && step > currentStage
                ? "stopped"
                : "pending";
          return (
            <li
              key={stage.label}
              className={`${styles.step} ${styles[`step${state[0].toUpperCase()}${state.slice(1)}`]}`}
              aria-current={step === currentStage ? "step" : undefined}
            >
              <span className={styles.stepNumber} aria-hidden="true">
                {stage.complete ? "✓" : step}
              </span>
              <span>
                <strong>{stage.label}</strong>
                <small>{stage.detail}</small>
              </span>
            </li>
          );
        })}
      </ol>

      <dl className={styles.summary}>
        <div>
          <dt>Requested amount</dt>
          <dd>{money(expanded.requested_amount)}</dd>
        </div>
        <div>
          <dt>Requested tenure</dt>
          <dd>
            {expanded.requested_tenure_months
              ? `${expanded.requested_tenure_months} months`
              : "Loan type default"}
          </dd>
        </div>
        <div>
          <dt>Preferred disbursement</dt>
          <dd>{expanded.preferred_disbursement_date || "No preference"}</dd>
        </div>
        <div>
          <dt>Transfer reference</dt>
          <dd>{expanded.payment_reference}</dd>
        </div>
        <div>
          <dt>Fee snapshot</dt>
          <dd>{money(expanded.form_fee_amount)}</dd>
        </div>
        <div>
          <dt>Payment status</dt>
          <dd>{PAYMENT_STATUS_LABELS[expanded.payment_status]}</dd>
        </div>
        <div className={styles.full}>
          <dt>Payout account</dt>
          <dd>
            {expanded.use_default_account
              ? "Member's default account"
              : `${expanded.alternate_bank_name}, ${expanded.alternate_account_name}, ${expanded.alternate_account_number}`}
          </dd>
        </div>
        {expanded.member_notes && (
          <div className={styles.full}>
            <dt>Member's reason</dt>
            <dd>{expanded.member_notes}</dd>
          </div>
        )}
      </dl>

      {expanded.was_restricted_at_submission && (
        <p className={`${styles.notice} ${styles.warning}`}>
          This member was loan-restricted when they submitted.
          {expanded.restriction_reason_snapshot && ` Reason: ${expanded.restriction_reason_snapshot}`}
        </p>
      )}

      <div className={styles.receipt}>
        <h3>Payment receipt</h3>
        <ReceiptPreview
          contentType={expanded.receipt_content_type}
          base64={expanded.receipt_image_base64}
        />
      </div>

      {expanded.payment_rejection_reason && (
        <p className={`${styles.notice} ${styles.danger}`}>
          Payment rejected: {expanded.payment_rejection_reason}
        </p>
      )}

      {readOnly && <ConflictNotice entity="application" />}

      {!readOnly && expanded.payment_status === "awaiting_verification" && (
        <section className={styles.actionPanel} aria-labelledby="verify-payment-heading">
          <h3 id="verify-payment-heading">1. Review and verify payment</h3>
          <p>Confirm the receipt matches the fee snapshot before making the loan decision.</p>
          <label className={styles.field}>
            Rejection reason (required if rejecting)
            <input
              value={form.rejectionReason}
              onChange={(event) => form.setRejectionReason(event.target.value)}
            />
          </label>
          <div className={styles.actions}>
            <button
              type="button"
              className="btn btn-danger"
              onClick={() => review.onVerifyPayment(false)}
            >
              Reject payment
            </button>
            <button
              type="button"
              className="btn btn-primary"
              onClick={() => review.onVerifyPayment(true)}
            >
              Verify payment
            </button>
          </div>
        </section>
      )}

      {!readOnly && expanded.payment_status === "verified" && expanded.status === "pending" && (
        <section className={styles.actionPanel} aria-labelledby="loan-decision-heading">
          <h3 id="loan-decision-heading">2. Approve or reject</h3>
          <p>
            Payment is verified. Approval freezes the interest rate, interest method and fee
            snapshot for disbursement.
          </p>
          <div className={styles.fields}>
            <label className={styles.field}>
              Approved amount
              <input
                type="number"
                min="0.01"
                step="0.01"
                value={form.approvedAmount}
                onChange={(event) => form.setApprovedAmount(event.target.value)}
              />
            </label>
            <label className={styles.field}>
              Approved tenure (months)
              <input
                type="number"
                min="1"
                step="1"
                value={form.approvedTenureMonths}
                onChange={(event) => form.setApprovedTenureMonths(event.target.value)}
              />
            </label>
            <label className={`${styles.field} ${styles.full}`}>
              Tenure decision reason (if different from the request)
              <input
                value={form.tenureDecisionReason}
                onChange={(event) => form.setTenureDecisionReason(event.target.value)}
              />
            </label>
            <label className={`${styles.field} ${styles.full}`}>
              Admin notes (sent to the member if rejected)
              <textarea
                rows={3}
                value={form.adminNotes}
                onChange={(event) => form.setAdminNotes(event.target.value)}
              />
            </label>
          </div>
          <label className={styles.checkbox}>
            <input
              type="checkbox"
              checked={form.canReapply}
              onChange={(event) => form.setCanReapply(event.target.checked)}
            />
            Member may reapply if rejected
          </label>
          <div className={styles.actions}>
            <button
              type="button"
              className="btn btn-danger"
              onClick={() => review.onDecide(false)}
            >
              Reject loan
            </button>
            <button
              type="button"
              className="btn btn-primary"
              onClick={() => review.onDecide(true)}
            >
              Approve loan
            </button>
          </div>
        </section>
      )}

      {!readOnly && expanded.status === "approved" && !expanded.resulting_loan_id && (
        <section className={styles.actionPanel} aria-labelledby="disburse-heading">
          <h3 id="disburse-heading">3. Disburse approved loan</h3>
          <dl className={styles.summary}>
            <div>
              <dt>Approved amount</dt>
              <dd>{money(expanded.approved_amount)}</dd>
            </div>
            <div>
              <dt>Approved tenure</dt>
              <dd>{expanded.approved_tenure_months} months</dd>
            </div>
            <div>
              <dt>Frozen interest rate</dt>
              <dd>
                {expanded.approved_interest_rate
                  ? `${(parseFloat(expanded.approved_interest_rate) * 100).toFixed(2)}%`
                  : "Resolved at disbursement (legacy approval)"}
              </dd>
            </div>
            <div>
              <dt>Frozen interest method</dt>
              <dd>
                {expanded.approved_interest_mode
                  ? INTEREST_MODE_LABELS[expanded.approved_interest_mode]
                  : "Resolved at disbursement (legacy approval)"}
              </dd>
            </div>
            {expanded.approved_interest_mode === "spread_first_months" && (
              <div>
                <dt>Interest spread period</dt>
                <dd>{expanded.approved_interest_spread_months} months</dd>
              </div>
            )}
            {expanded.tenure_decision_reason && (
              <div className={styles.full}>
                <dt>Tenure decision reason</dt>
                <dd>{expanded.tenure_decision_reason}</dd>
              </div>
            )}
          </dl>
          <p className={`${styles.notice} ${styles.success}`}>
            The {money(expanded.form_fee_amount)} fee was paid with this application. It will not
            be requested again after disbursement.
          </p>
          <p>
            Disbursement creates the active loan, sets the date to the 1st of this month, and
            emails the member with the repayment details.
          </p>
          <div className={styles.actions}>
            <button
              type="button"
              className="btn btn-primary"
              onClick={() => review.onDisburse(expanded.id)}
            >
              Disburse now
            </button>
          </div>
        </section>
      )}

      {(expanded.status === "rejected" || expanded.status === "cancelled") && (
        <p className={`${styles.notice} ${styles.danger}`}>
          This application was {expanded.status}. No loan can be disbursed from it.
        </p>
      )}

      {expanded.resulting_loan_id && (
        <p className={`${styles.notice} ${styles.success}`}>
          Disbursed. The application fee is settled and no second fee payment is due.
        </p>
      )}
    </section>
  );
}
