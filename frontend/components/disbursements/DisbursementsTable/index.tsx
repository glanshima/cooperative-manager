import Table from "@/components/ui/Table";
import { ConflictMarker } from "@/components/ui/ConflictMarker";
import type { DisbursementsPageModel } from "../hooks/useDisbursementsPage";

export default function DisbursementsTable({
  table,
}: {
  table: DisbursementsPageModel["table"];
}) {
  if (table.items.length === 0) {
    return <p>No approved loans are currently waiting to be disbursed.</p>;
  }

  return (
    <Table style={{ marginBottom: 24 }}>
      <thead>
        <tr style={{ textAlign: "left", borderBottom: "2px solid #333" }}>
          <th>Member</th>
          <th>Loan type</th>
          <th>Approved amount</th>
          <th>Tenure</th>
          <th>Preferred date</th>
          <th>Account</th>
          <th></th>
        </tr>
      </thead>
      <tbody>
        {table.items.map((a) => (
          <tr key={a.id} style={{ borderBottom: "1px solid #eee" }}>
            <td>
              {a.member_name} ({a.member_psn?.replace("MCT-", "") ?? ""})
            </td>
            <td>{a.loan_type_name}</td>
            <td>{a.approved_amount}</td>
            <td>{a.approved_tenure_months}mo</td>
            <td>{a.preferred_disbursement_date || "—"}</td>
            <td>
              {a.use_default_account
                ? "Default"
                : `${a.alternate_bank_name} / ${a.alternate_account_name}`}
            </td>
            <td>
              {a.conflicted ? <ConflictMarker /> : <button onClick={() => table.onDisburse(a)}>Disburse</button>}
            </td>
          </tr>
        ))}
      </tbody>
    </Table>
  );
}
