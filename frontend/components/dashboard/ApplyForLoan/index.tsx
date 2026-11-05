import type { Member, Settings } from "@/lib/api";
import type { DashboardPageModel } from "../hooks/useDashboardPage";

export default function ApplyForLoan({
  apply,
  member,
  settings,
}: {
  apply: DashboardPageModel["apply"];
  member: Member | null;
  settings: Settings | null;
}) {
  const { form, preview, selectedType, applyableTypes } = apply;

  return (
    <>
      <section style={{ marginBottom: 24 }}>
        <button onClick={apply.toggle}>{apply.showForm ? "Cancel" : "Apply for a loan"}</button>
      </section>

      {apply.showForm && (
        <section
          style={{
            border: "1px solid #ddd",
            borderRadius: 8,
            padding: 16,
            marginBottom: 24,
          }}
        >
          <h2>New loan application</h2>
          <p style={{ color: "#555" }}>
            A loan-form fee of <strong>{settings?.loan_form_fee}</strong> must be paid by bank
            transfer before your application can be reviewed. Enter your transfer reference and
            attach a photo/scan of the receipt below.
          </p>

          <form onSubmit={apply.submit} style={{ display: "grid", gap: 10 }}>
            <select
              required
              value={form.loan_type_id}
              onChange={(e) => apply.setField("loan_type_id", e.target.value)}
            >
              <option value="">Select loan type</option>
              {applyableTypes.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.name} ({(parseFloat(t.interest_rate) * 100).toFixed(1)}%, {t.tenure_months}mo)
                </option>
              ))}
            </select>

            {selectedType?.description && (
              <p style={{ fontSize: 13, color: "#666", margin: 0 }}>{selectedType.description}</p>
            )}

            <input
              required
              type="number"
              step="0.01"
              placeholder="Amount requested"
              value={form.requested_amount || ""}
              onChange={(e) => apply.setField("requested_amount", parseFloat(e.target.value) || 0)}
            />

            <label>
              Requested tenure in months (optional — leave blank to use the default; can only be
              shorter than or equal to the default):
              <input
                type="number"
                placeholder="e.g. 12"
                value={form.requested_tenure_months}
                onChange={(e) =>
                  apply.setField(
                    "requested_tenure_months",
                    e.target.value ? parseInt(e.target.value) : ""
                  )
                }
              />
            </label>

            <label>
              Preferred disbursement date (a preference only — actual disbursement timing is set
              by the cooperative):
              <input
                type="date"
                value={form.preferred_disbursement_date}
                onChange={(e) => apply.setField("preferred_disbursement_date", e.target.value)}
              />
            </label>

            {selectedType && form.requested_amount > 0 && (
              <div
                style={{
                  background: "#f6f6f6",
                  padding: 10,
                  borderRadius: 6,
                  fontSize: 14,
                }}
              >
                <strong>Estimated terms</strong> (final terms are set by the cooperative at
                approval, and may differ):
                <div>Interest (deducted at source): {preview.interest.toFixed(2)}</div>
                <div>Amount you would receive: {preview.netDisbursed.toFixed(2)}</div>
                {preview.flatCharge > 0 && <div>Flat charge: {preview.flatCharge.toFixed(2)}</div>}
                <div>Total repayable: {preview.totalRepayable.toFixed(2)}</div>
                <div>
                  Monthly installment ({preview.tenure} months): {preview.installment.toFixed(2)}
                </div>
              </div>
            )}

            <label>
              <input
                type="checkbox"
                checked={form.use_default_account}
                onChange={(e) => apply.setField("use_default_account", e.target.checked)}
              />{" "}
              Send funds to my account on file
              {member?.account_number ? ` (${member.account_number})` : ""}
            </label>
            {!form.use_default_account && (
              <div style={{ display: "grid", gap: 8 }}>
                <input
                  required
                  placeholder="Bank name"
                  value={form.alternate_bank_name}
                  onChange={(e) => apply.setField("alternate_bank_name", e.target.value)}
                />
                <input
                  required
                  placeholder="Account name"
                  value={form.alternate_account_name}
                  onChange={(e) => apply.setField("alternate_account_name", e.target.value)}
                />
                <input
                  required
                  placeholder="Account number"
                  value={form.alternate_account_number}
                  onChange={(e) => apply.setField("alternate_account_number", e.target.value)}
                />
              </div>
            )}

            <textarea
              placeholder="Notes (optional) - e.g. reason for the loan"
              value={form.member_notes}
              onChange={(e) => apply.setField("member_notes", e.target.value)}
            />

            <input
              required
              placeholder="Bank transfer reference number"
              value={form.payment_reference}
              onChange={(e) => apply.setField("payment_reference", e.target.value)}
            />

            <label>
              Payment receipt (photo or PDF):
              <input
                required
                type="file"
                accept="image/*,application/pdf"
                onChange={(e) => apply.setReceiptFile(e.target.files?.[0] || null)}
              />
            </label>

            <button type="submit">Submit application</button>
          </form>
        </section>
      )}
    </>
  );
}
