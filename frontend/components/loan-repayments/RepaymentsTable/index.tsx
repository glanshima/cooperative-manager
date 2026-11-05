import Table from "@/components/ui/Table";
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
          <th>Reference</th>
          <th>Status</th>
          <th></th>
        </tr>
      </thead>
      <tbody>
        {table.items.map((r) => (
          <tr key={r.id} style={{ borderBottom: "1px solid #eee" }}>
            <td>{r.amount_claimed}</td>
            <td>{r.payment_reference}</td>
            <td>{r.status}</td>
            <td>
              <button onClick={() => table.onReview(r.id)}>Review</button>
            </td>
          </tr>
        ))}
      </tbody>
    </Table>
  );
}
