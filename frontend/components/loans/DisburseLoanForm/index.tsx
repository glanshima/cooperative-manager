import type { LoansPageModel } from "../hooks/useLoansPage";

export default function DisburseLoanForm({ disburse }: { disburse: LoansPageModel["disburse"] }) {
  const { form, preview, selectedType } = disburse;

  return (
    <section
      style={{
        border: "1px solid #ddd",
        borderRadius: 8,
        padding: 16,
        marginBottom: 24,
      }}
    >
      <h2>Disburse a loan</h2>
      <form
        onSubmit={disburse.submit}
        style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}
      >
        <select
          required
          value={form.member_id}
          onChange={(e) => disburse.setField("member_id", e.target.value)}
        >
          <option value="">Select member</option>
          {disburse.members.map((m) => (
            <option key={m.id} value={m.id}>
              {m.name} ({m.psn})
            </option>
          ))}
        </select>

        <select
          required
          value={form.loan_type_id}
          onChange={(e) => disburse.setField("loan_type_id", e.target.value)}
        >
          <option value="">Select loan type</option>
          {disburse.activeTypes.map((t) => (
            <option key={t.id} value={t.id}>
              {t.name} ({(parseFloat(t.interest_rate) * 100).toFixed(1)}%, {t.tenure_months}mo)
            </option>
          ))}
        </select>

        <input
          required
          type="number"
          step="0.01"
          placeholder="Principal amount"
          value={form.principal || ""}
          onChange={(e) => disburse.setField("principal", parseFloat(e.target.value) || 0)}
        />

        <input
          required
          type="date"
          value={form.disbursement_date}
          onChange={(e) => disburse.setField("disbursement_date", e.target.value)}
        />

        <input
          placeholder="Notes (optional)"
          value={form.notes || ""}
          onChange={(e) => disburse.setField("notes", e.target.value)}
          style={{ gridColumn: "1 / -1" }}
        />

        {selectedType && form.principal > 0 && (
          <div
            style={{
              gridColumn: "1 / -1",
              background: "#f6f6f6",
              padding: 8,
              borderRadius: 6,
              fontSize: 14,
            }}
          >
            Interest (deducted at source): {preview.interest.toFixed(2)} · Amount paid out:{" "}
            {preview.netDisbursed.toFixed(2)}
            {preview.flatCharge > 0 && ` · Flat charge: ${preview.flatCharge.toFixed(2)}`}
            {" "}· Total repayable: {preview.total.toFixed(2)} · Monthly installment:{" "}
            {preview.installment.toFixed(2)}
          </div>
        )}

        <div style={{ gridColumn: "1 / -1" }}>
          <button type="submit">Disburse loan</button>
        </div>
      </form>
    </section>
  );
}
