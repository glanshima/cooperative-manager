import Table from "@/components/ui/Table";
import { INTEREST_MODE_LABELS } from "@/lib/loanMath";
import type { LoansPageModel } from "../hooks/useLoansPage";
import RateHistoryPanel from "../RateHistoryPanel";

export default function LoanTypesManager({ types }: { types: LoansPageModel["types"] }) {
  const { form } = types;

  return (
    <section
      style={{
        border: "1px solid #ddd",
        borderRadius: 8,
        padding: 16,
        marginBottom: 24,
      }}
    >
      <h2>Loan types</h2>
      <p className="notice">
        Every loan type uses the universal loan/application fee configured in Settings. Legacy
        fee values below are kept for history only.
      </p>
      <Table style={{ marginBottom: 16 }}>
        <thead>
          <tr style={{ textAlign: "left", borderBottom: "2px solid #333" }}>
            <th>Name</th>
            <th>Description</th>
            <th>Rate</th>
            <th>Tenure (months)</th>
            <th>Interest deduction</th>
            <th>Legacy fee (history only)</th>
            <th>Active</th>
            <th>Open for application</th>
          </tr>
        </thead>
        <tbody>
          {types.items.map((t) => (
            <tr key={t.id} style={{ borderBottom: "1px solid #eee" }}>
              <td>{t.name}</td>
              <td style={{ maxWidth: 200, fontSize: 13, color: "#555" }}>
                {t.description || "—"}
              </td>
              <td>{(parseFloat(t.interest_rate) * 100).toFixed(2)}%</td>
              <td>{t.tenure_months}</td>
              <td>
                {t.interest_mode
                  ? INTEREST_MODE_LABELS[t.interest_mode]
                  : "Cooperative default"}
                {t.interest_mode === "spread_first_months" &&
                  t.interest_spread_months &&
                  ` (${t.interest_spread_months}mo)`}
              </td>
              <td>{parseFloat(t.flat_charge) > 0 ? t.flat_charge : "—"}</td>
              <td>
                <button onClick={() => types.onToggleActive(t)}>
                  {t.is_active ? "Deactivate" : "Activate"}
                </button>
              </td>
              <td>
                <button onClick={() => types.onToggleOpenForApplication(t)}>
                  {t.open_for_application ? "Close to members" : "Open to members"}
                </button>{" "}
                <button onClick={() => types.showHistory(t)}>Rate history</button>
              </td>
            </tr>
          ))}
        </tbody>
      </Table>

      <RateHistoryPanel types={types} />

      <h3>Add loan type</h3>
      <form onSubmit={types.submit} className="form-grid">
        <input
          required
          placeholder="Name (e.g. Capital Loan)"
          value={form.name}
          onChange={(e) => types.setField("name", e.target.value)}
        />
        <input
          placeholder="Short description (optional)"
          value={form.description}
          onChange={(e) => types.setField("description", e.target.value)}
        />
        <input
          required
          type="number"
          step="0.0001"
          placeholder="Interest rate (e.g. 0.15 for 15%)"
          value={form.interest_rate}
          onChange={(e) => types.setField("interest_rate", parseFloat(e.target.value))}
        />
        <input
          required
          type="number"
          placeholder="Tenure (months)"
          value={form.tenure_months}
          onChange={(e) => types.setField("tenure_months", parseInt(e.target.value))}
        />
        <select
          aria-label="Interest deduction"
          value={form.interest_mode}
          onChange={(e) =>
            types.setField(
              "interest_mode",
              e.target.value as typeof form.interest_mode
            )
          }
        >
          <option value="">Use the cooperative default</option>
          {Object.entries(INTEREST_MODE_LABELS).map(([mode, label]) => (
            <option key={mode} value={mode}>
              {label}
            </option>
          ))}
        </select>
        {form.interest_mode === "spread_first_months" && (
          <input
            required
            type="number"
            min={1}
            max={form.tenure_months}
            placeholder="Months the interest is spread over"
            value={form.interest_spread_months}
            onChange={(e) =>
              types.setField(
                "interest_spread_months",
                parseInt(e.target.value) || ""
              )
            }
          />
        )}
        <input
          required
          type="date"
          value={form.effective_from}
          onChange={(e) => types.setField("effective_from", e.target.value)}
        />
        <div className="form-grid__full">
          <button type="submit">Add loan type</button>
        </div>
      </form>
    </section>
  );
}
