import Table from "@/components/ui/Table";
import { ConflictMarker } from "@/components/ui/ConflictMarker";
import type { PaymentVerificationStatus } from "@/lib/api";
import type { LoanFeesPageModel } from "../hooks/useLoanFeesPage";

const STATUS_LABELS: Record<PaymentVerificationStatus, string> = {
  awaiting_verification: "Awaiting verification",
  verified: "Verified",
  rejected: "Rejected",
};

export default function FeePaymentsTable({
  table,
}: {
  table: LoanFeesPageModel["table"];
}) {
  if (table.items.length === 0) {
    return <p>Nothing to review.</p>;
  }

  return (
    <Table style={{ marginBottom: 24 }}>
      <thead>
        <tr style={{ textAlign: "left", borderBottom: "2px solid #333" }}>
          <th>PSN</th>
          <th>Member</th>
          <th>Loan type</th>
          <th>Fee amount</th>
          <th>Reference</th>
          <th>Status</th>
          <th>Submitted</th>
          <th></th>
        </tr>
      </thead>
      <tbody>
        {table.items.map((p) => (
          <tr key={p.id} style={{ borderBottom: "1px solid #eee" }}>
            <td>{p.member_psn}</td>
            <td>{p.member_name}</td>
            <td>{p.loan_type_name || "—"}</td>
            <td>{p.amount}</td>
            <td>{p.payment_reference}</td>
            <td>
              {STATUS_LABELS[p.status]}
              {p.conflicted && (
                <div style={{ fontSize: 12 }}>
                  <ConflictMarker />
                </div>
              )}
            </td>
            <td>{new Date(p.created_at).toLocaleString()}</td>
            <td>
              <button onClick={() => table.onReview(p.id)}>Review</button>
            </td>
          </tr>
        ))}
      </tbody>
    </Table>
  );
}
