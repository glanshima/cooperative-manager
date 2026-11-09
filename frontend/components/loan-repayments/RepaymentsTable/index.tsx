import Table from "@/components/ui/Table";
import { ConflictMarker } from "@/components/ui/ConflictMarker";
import { monthLabel } from "@/lib/month";
import type { LoanRepaymentsPageModel } from "../hooks/useLoanRepaymentsPage";

export default function RepaymentsTable({
  table,
}: {
  table: LoanRepaymentsPageModel["table"];
}) {
  return (
    <Table style={{ marginBottom: 24 }}>
      <thead>
        <tr style={{ textAlign: "left", borderBottom: "2px solid #333" }}>
          <th>Amount claimed</th>
          <th>Month paid</th>
          <th>Reference</th>
          <th>Status</th>
          <th></th>
        </tr>
      </thead>
      <tbody>
        {table.items.map((r) => (
          <tr key={r.id} style={{ borderBottom: "1px solid #eee" }}>
            <td>{r.amount_claimed}</td>
            <td>
              {r.payment_month ? (
                monthLabel(r.payment_month)
              ) : (
                <span style={{ color: "#b45309" }} title="Recorded before the payment month was captured">
                  Not recorded
                </span>
              )}
            </td>
            <td>{r.payment_reference}</td>
            <td>
              {r.status}
              {/* Review stays available -- reading is permitted; the panel
                  hides the verify/reject actions. */}
              {r.conflicted && <div style={{ fontSize: 12 }}><ConflictMarker /></div>}
            </td>
            <td>
              <button onClick={() => table.onReview(r.id)}>Review</button>
            </td>
          </tr>
        ))}
      </tbody>
    </Table>
  );
}
