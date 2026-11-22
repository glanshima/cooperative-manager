import CloseButton from "@/components/ui/CloseButton";
import ReceiptPreview from "@/components/ui/ReceiptPreview";
import { ConflictNotice } from "@/components/ui/ConflictMarker";
import type { LoanFeesPageModel } from "../hooks/useLoanFeesPage";

export default function FeeReviewPanel({ review }: { review: LoanFeesPageModel["review"] }) {
  const payment = review.payment;
  if (!payment) return null;

  const readOnly = Boolean(payment.conflicted);

  return (
    <section
      style={{
        border: "1px solid #ddd",
        borderRadius: 8,
        padding: 16,
      }}
    >
      <div style={{ display: "flex", alignItems: "flex-start", gap: 12 }}>
        <h2 style={{ flex: 1 }}>Reviewing fee payment of {payment.amount}</h2>
        <CloseButton label="Close fee review" onClick={review.close} />
      </div>
      <p>Payment reference: {payment.payment_reference}</p>
      <p style={{ fontSize: 13, color: "#666" }}>
        This is cooperative income paid separately from the loan. Verifying it
        records the fee as settled; it never changes the loan's payout, total or
        balance.
      </p>

      <div style={{ margin: "12px 0" }}>
        <ReceiptPreview
          contentType={payment.receipt_content_type}
          base64={payment.receipt_image_base64}
        />
      </div>

      {readOnly && <ConflictNotice entity="fee payment" />}

      {!readOnly && payment.status === "awaiting_verification" && (
        <div style={{ display: "grid", gap: 8 }}>
          <input
            placeholder="Rejection reason (if rejecting)"
            value={review.rejectionReason}
            onChange={(e) => review.setRejectionReason(e.target.value)}
          />
          <div>
            <button onClick={() => review.verify(true)}>Verify fee payment</button>{" "}
            <button onClick={() => review.verify(false)}>Reject fee payment</button>
          </div>
        </div>
      )}
    </section>
  );
}
