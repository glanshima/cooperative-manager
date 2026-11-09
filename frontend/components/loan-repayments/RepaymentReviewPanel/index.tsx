import ReceiptPreview from "@/components/ui/ReceiptPreview";
import { ConflictNotice } from "@/components/ui/ConflictMarker";
import { monthLabel } from "@/lib/month";
import type { LoanRepaymentsPageModel } from "../hooks/useLoanRepaymentsPage";

export default function RepaymentReviewPanel({
  review,
}: {
  review: LoanRepaymentsPageModel["review"];
}) {
  const repayment = review.repayment;
  if (!repayment) return null;

  const readOnly = Boolean(repayment.conflicted);

  return (
    <section
      style={{
        border: "1px solid #ddd",
        borderRadius: 8,
        padding: 16,
      }}
    >
      <h2>Reviewing repayment of {repayment.amount_claimed}</h2>
      <p>Payment reference: {repayment.payment_reference}</p>
      <p>
        Month paid:{" "}
        {repayment.payment_month ? (
          monthLabel(repayment.payment_month)
        ) : (
          <span style={{ color: "#b45309" }}>
            not recorded — confirm with the member which payroll month this covers
          </span>
        )}
      </p>

      <div style={{ margin: "12px 0" }}>
        <ReceiptPreview
          contentType={repayment.receipt_content_type}
          base64={repayment.receipt_image_base64}
        />
      </div>

      {readOnly && <ConflictNotice entity="repayment" />}

      {!readOnly && repayment.status === "awaiting_verification" && (
        <div style={{ display: "grid", gap: 8 }}>
          <input
            placeholder="Rejection reason (if rejecting)"
            value={review.rejectionReason}
            onChange={(e) => review.setRejectionReason(e.target.value)}
          />
          <div>
            <button onClick={() => review.verify(true)}>Verify repayment</button>{" "}
            <button onClick={() => review.verify(false)}>Reject repayment</button>
          </div>
        </div>
      )}

      <button onClick={review.close} style={{ marginTop: 12 }}>
        Close
      </button>
    </section>
  );
}
