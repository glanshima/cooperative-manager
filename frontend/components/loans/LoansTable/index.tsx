import Table from "@/components/ui/Table";
import { ConflictMarker } from "@/components/ui/ConflictMarker";
import type { LoansPageModel } from "../hooks/useLoansPage";

export default function LoansTable({ table }: { table: LoansPageModel["table"] }) {
  return (
    <section>
      <h2>All loans</h2>
      {table.loading ? (
        <p>Loading...</p>
      ) : (
        <Table>
          <thead>
            <tr style={{ textAlign: "left", borderBottom: "2px solid #333" }}>
              <th>Member</th>
              <th>Type</th>
              <th>Principal</th>
              <th>Net disbursed</th>
              <th>Balance</th>
              <th>Status</th>
              <th>Disbursed</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {table.items.map((loan) => (
              <tr key={loan.id} style={{ borderBottom: "1px solid #eee" }}>
                <td>
                  {loan.member_name} ({loan.member_psn?.replace("MCT-", "") ?? ""})
                </td>
                <td>{loan.loan_type_name}</td>
                <td>{loan.principal}</td>
                <td>{loan.net_disbursed}</td>
                <td>{loan.balance}</td>
                <td>{loan.status}</td>
                <td>{loan.disbursement_date}</td>
                <td>
                  {loan.conflicted ? (
                    <ConflictMarker />
                  ) : (
                    <>
                      <button onClick={() => table.onRecordRepayment(loan)}>Record repayment</button>{" "}
                      <button onClick={() => table.onDelete(loan.id)}>Delete</button>
                    </>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </Table>
      )}
    </section>
  );
}
