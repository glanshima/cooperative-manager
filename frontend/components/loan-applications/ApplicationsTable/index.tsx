import Table from "@/components/ui/Table";
import { ConflictMarker } from "@/components/ui/ConflictMarker";
import type { LoanApplicationsPageModel } from "../hooks/useLoanApplicationsPage";

export default function ApplicationsTable({
  table,
}: {
  table: LoanApplicationsPageModel["table"];
}) {
  return (
    <Table style={{ marginBottom: 24 }}>
      <thead>
        <tr style={{ textAlign: "left", borderBottom: "2px solid #333" }}>
          <th>Member</th>
          <th>Type</th>
          <th>Requested</th>
          <th>Payment</th>
          <th>Status</th>
          <th>Flag</th>
          <th></th>
        </tr>
      </thead>
      <tbody>
        {table.items.map((a) => (
          <tr key={a.id} style={{ borderBottom: "1px solid #eee" }}>
            <td>
              {a.member_name} ({a.member_psn})
            </td>
            <td>{a.loan_type_name}</td>
            <td>{a.requested_amount}</td>
            <td>{a.payment_status}</td>
            <td>{a.status}</td>
            <td>
              {a.was_restricted_at_submission && (
                <span style={{ color: "#b45309", fontWeight: 600 }}>⚠ restricted</span>
              )}{" "}
              {a.conflicted && <ConflictMarker />}
            </td>
            <td>
              {/* Review is a read, so a conflicted officer may still open it --
                  the panel disables the actions. Disbursing is a write, so the
                  button doesn't appear for them at all. */}
              <button onClick={() => table.onReview(a.id)}>Review</button>{" "}
              {!a.conflicted && a.status === "approved" && !a.resulting_loan_id && (
                <button onClick={() => table.onDisburse(a.id)}>Disburse</button>
              )}
            </td>
          </tr>
        ))}
      </tbody>
    </Table>
  );
}
