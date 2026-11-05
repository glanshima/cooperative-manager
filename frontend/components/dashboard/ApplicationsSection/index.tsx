import { Fragment } from "react";
import Table from "@/components/ui/Table";
import type { DashboardPageModel } from "../hooks/useDashboardPage";

export default function ApplicationsSection({
  applications,
}: {
  applications: DashboardPageModel["applications"];
}) {
  const { items, onReschedule, onCancel, onStartReapply } = applications;

  return (
    <section style={{ marginBottom: 24 }}>
      <h2>My applications</h2>
      {items.length === 0 ? (
        <p>No applications yet.</p>
      ) : (
        <Table>
          <thead>
            <tr style={{ textAlign: "left", borderBottom: "2px solid #333" }}>
              <th>Loan type</th>
              <th>Requested</th>
              <th>Tenure req.</th>
              <th>Approved</th>
              <th>Payment</th>
              <th>Status</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {items.map((a) => {
              const rejectionNote =
                a.payment_status === "rejected"
                  ? a.payment_rejection_reason
                  : a.status === "rejected"
                  ? a.admin_notes
                  : null;
              const canCancelOrReschedule =
                a.status === "pending" || (a.status === "approved" && !a.resulting_loan_id);
              const canReapply = a.status === "rejected" && a.can_reapply;
              return (
                <Fragment key={a.id}>
                  <tr style={{ borderBottom: rejectionNote ? "none" : "1px solid #eee" }}>
                    <td>{a.loan_type_name}</td>
                    <td>{a.requested_amount}</td>
                    <td>{a.requested_tenure_months ? `${a.requested_tenure_months}mo` : "default"}</td>
                    <td>{a.approved_amount || "—"}</td>
                    <td>{a.payment_status}</td>
                    <td>{a.status}</td>
                    <td>
                      {canCancelOrReschedule && (
                        <>
                          <button onClick={() => onReschedule(a.id)}>Reschedule</button>{" "}
                          <button onClick={() => onCancel(a.id)}>Cancel</button>
                        </>
                      )}
                      {canReapply && <button onClick={() => onStartReapply(a)}>Reapply</button>}
                    </td>
                  </tr>
                  {rejectionNote && (
                    <tr style={{ borderBottom: "1px solid #eee" }}>
                      <td colSpan={7} style={{ color: "#b91c1c", fontSize: 13, paddingBottom: 8 }}>
                        Reason: {rejectionNote}
                      </td>
                    </tr>
                  )}
                </Fragment>
              );
            })}
          </tbody>
        </Table>
      )}
    </section>
  );
}
