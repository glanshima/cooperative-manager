import Table from "@/components/ui/Table";
import type { Loan } from "@/lib/api";
import type { DashboardPageModel } from "../hooks/useDashboardPage";

const FEE_STATUS_LABELS: Record<NonNullable<Loan["fee_status"]>, string> = {
  not_required: "—",
  due: "Due",
  awaiting_verification: "Awaiting verification",
  rejected: "Rejected",
  paid: "Paid",
};

export default function LoansSection({ loans }: { loans: DashboardPageModel["loans"] }) {
  const feePayable = (feeStatus: Loan["fee_status"]) =>
    feeStatus === "due" || feeStatus === "rejected";

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
              <th>Loan fee</th>
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
                <td>
                  {loan.fee_status ? FEE_STATUS_LABELS[loan.fee_status] : "—"}
                  {feePayable(loan.fee_status) && ` (${loan.fee_amount})`}
                  {loan.fee_status === "rejected" && loan.fee_rejection_reason && (
                    <div style={{ fontSize: 13, color: "#a33" }}>
                      {loan.fee_rejection_reason}
                    </div>
                  )}
                </td>
                <td>{loan.status}</td>
                <td>{loan.expected_end_date}</td>
                <td>
                  {loan.status === "active" && (
                    <button onClick={() => loans.startRepayment(loan)}>Make a repayment</button>
                  )}
                  {feePayable(loan.fee_status) &&
                    !loan.conflicted && (
                      <>
                        {" "}
                        <button onClick={() => loans.startFeePayment(loan)}>
                          {loan.fee_status === "rejected" ? "Resubmit fee" : "Pay fee"}
                        </button>
                      </>
                    )}
                </td>
              </tr>
            ))}
          </tbody>
        </Table>
      )}

      {loans.feePayingLoanId && (
        <section
          style={{
            border: "1px solid #ddd",
            borderRadius: 8,
            padding: 16,
            marginTop: 16,
          }}
        >
          <h3>Pay the loan fee</h3>
          <p style={{ fontSize: 13, color: "#666", marginTop: 0 }}>
            The loan fee is separate from your loan. Pay it to the cooperative and attach
            the receipt — a staff member verifies it. It is never added to what you repay.
          </p>
          <form onSubmit={loans.submitFeePayment} style={{ display: "grid", gap: 10 }}>
            <input
              required
              placeholder="Bank transfer reference number"
              value={loans.feeReference}
              onChange={(e) => loans.setFeeReference(e.target.value)}
            />
            <label>
              Payment receipt (photo or PDF):
              <input
                required
                type="file"
                accept="image/*,application/pdf"
                onChange={(e) => loans.setFeeReceiptFile(e.target.files?.[0] || null)}
              />
            </label>
            <div>
              <button type="submit">Submit fee payment</button>{" "}
              <button type="button" onClick={loans.cancelFeePayment}>
                Cancel
              </button>
            </div>
          </form>
        </section>
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
            <label>
              Month this payment covers:
              <input
                required
                type="month"
                aria-label="Month paid"
                value={loans.repayMonth}
                onChange={(e) => loans.setRepayMonth(e.target.value)}
              />
            </label>
            <span style={{ fontSize: 13, color: "#666" }}>
              Payroll skips the instalment for a month you have already paid
              directly, so pick the month the transfer was for.
            </span>
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
              <button type="submit" disabled={loans.submitting}>
                {loans.submitting ? "Submitting..." : "Submit repayment"}
              </button>{" "}
              <button type="button" onClick={loans.cancelRepayment} disabled={loans.submitting}>
                Cancel
              </button>
            </div>
          </form>
        </section>
      )}
    </section>
  );
}
