import Table from "@/components/ui/Table";
import type { DisbursementsPageModel } from "../hooks/useDisbursementsPage";

export default function DisburseDialog({
  dialog,
}: {
  dialog: DisbursementsPageModel["dialog"];
}) {
  const application = dialog.application;
  if (!application) return null;

  return (
    <section
      style={{
        border: "1px solid #ddd",
        borderRadius: 8,
        padding: 16,
      }}
    >
      <h2>
        Disburse {application.member_name}'s {application.loan_type_name} —{" "}
        {application.approved_amount}
      </h2>

      {dialog.activeLoans.length > 0 ? (
        <>
          <p style={{ color: "#555" }}>
            This member has {dialog.activeLoans.length} active loan(s). You can fully close out
            some or all of them against this disbursement (they'll be marked repaid and
            completed; the amount deducted reduces what the member actually receives). No
            partial deduction — selected loans always close out completely.
          </p>
          <label>
            <input
              type="checkbox"
              checked={dialog.deductAll}
              onChange={(e) => dialog.onToggleDeductAll(e.target.checked)}
            />{" "}
            Deduct all active loans
          </label>
          {!dialog.deductAll && (
            <Table style={{ marginTop: 8 }}>
              <thead>
                <tr style={{ textAlign: "left" }}>
                  <th></th>
                  <th>Type</th>
                  <th>Balance</th>
                </tr>
              </thead>
              <tbody>
                {dialog.activeLoans.map((loan) => (
                  <tr key={loan.id}>
                    <td>
                      <input
                        type="checkbox"
                        checked={dialog.selectedLoanIds.includes(loan.id)}
                        onChange={() => dialog.onToggleLoan(loan.id)}
                      />
                    </td>
                    <td>{loan.loan_type_name}</td>
                    <td>{loan.balance}</td>
                  </tr>
                ))}
              </tbody>
            </Table>
          )}
        </>
      ) : (
        <p style={{ color: "#555" }}>This member has no other active loans.</p>
      )}

      <div style={{ marginTop: 16 }}>
        <button onClick={dialog.confirm}>Confirm disburse</button>{" "}
        <button onClick={dialog.close}>Cancel</button>
      </div>
    </section>
  );
}
