import Table from "@/components/ui/Table";
import type { DashboardPageModel } from "../hooks/useDashboardPage";

export default function LoansSection({ loans }: { loans: DashboardPageModel["loans"] }) {
  return (
    <section>
      <h2>My loans</h2>
      {loans.items.length === 0 ? (
        <p>No active or past loans.</p>
      ) : (
        <Table>
          <thead>
            <tr style={{ textAlign: "left", borderBottom: "2px solid #333" }}>
              <th>Type</th>
              <th>Principal</th>
              <th>Monthly installment</th>
              <th>Balance</th>
              <th>Status</th>
              <th>Expected end</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {loans.items.map((loan) => (
              <tr key={loan.id} style={{ borderBottom: "1px solid #eee" }}>
                <td>{loan.loan_type_name}</td>
                <td>{loan.principal}</td>
                <td>{loan.monthly_installment}</td>
                <td>{loan.balance}</td>
                <td>{loan.status}</td>
                <td>{loan.expected_end_date}</td>
                <td>
                  {loan.status === "active" && (
                    <button onClick={() => loans.startRepayment(loan)}>Make a repayment</button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </Table>
      )}

      {loans.servicingLoanId && (
        <section
          style={{
            border: "1px solid #ddd",
            borderRadius: 8,
            padding: 16,
            marginTop: 16,
          }}
        >
          <h3>Submit a repayment</h3>
          <form onSubmit={loans.submitRepayment} style={{ display: "grid", gap: 10 }}>
            <input
              required
              type="number"
              step="0.01"
              placeholder="Amount paid"
              value={loans.repayAmount || ""}
              onChange={(e) => loans.setRepayAmount(parseFloat(e.target.value) || 0)}
            />
            <input
              required
              placeholder="Bank transfer reference number"
              value={loans.repayReference}
              onChange={(e) => loans.setRepayReference(e.target.value)}
            />
            <label>
              Payment receipt (photo or PDF):
              <input
                required
                type="file"
                accept="image/*,application/pdf"
                onChange={(e) => loans.setRepayReceiptFile(e.target.files?.[0] || null)}
              />
            </label>
            <div>
              <button type="submit">Submit repayment</button>{" "}
              <button type="button" onClick={loans.cancelRepayment}>
                Cancel
              </button>
            </div>
          </form>
        </section>
      )}
    </section>
  );
}
