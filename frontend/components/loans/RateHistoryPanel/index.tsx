import CloseButton from "@/components/ui/CloseButton";
import Table from "@/components/ui/Table";
import { INTEREST_MODE_LABELS } from "@/lib/loanMath";
import type { LoansPageModel } from "../hooks/useLoansPage";

export default function RateHistoryPanel({ types }: { types: LoansPageModel["types"] }) {
  const { historyFor, history, newVersion } = types;
  if (!historyFor) return null;

  return (
    <div
      style={{
        border: "1px solid #ccc",
        borderRadius: 8,
        padding: 12,
        marginBottom: 16,
        background: "#fafafa",
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: 12,
        }}
      >
        <h4 style={{ margin: 0 }}>Rate history — {historyFor.name}</h4>
        <CloseButton size="sm" label="Close rate history" onClick={types.closeHistory} />
      </div>
      <Table style={{ marginBottom: 12 }}>
        <thead>
          <tr style={{ textAlign: "left", borderBottom: "1px solid #ccc" }}>
            <th>Effective from</th>
            <th>Rate</th>
            <th>Tenure</th>
            <th>Fee</th>
            <th>Interest deduction</th>
          </tr>
        </thead>
        <tbody>
          {history.map((v) => (
            <tr key={v.id}>
              <td>{v.effective_from}</td>
              <td>{(parseFloat(v.interest_rate) * 100).toFixed(2)}%</td>
              <td>{v.tenure_months}mo</td>
              <td>{parseFloat(v.flat_charge) > 0 ? v.flat_charge : "—"}</td>
              <td>
                {v.interest_mode ? INTEREST_MODE_LABELS[v.interest_mode] : "From loan type"}
                {v.interest_mode === "spread_first_months" && v.interest_spread_months
                  ? ` (${v.interest_spread_months}mo)`
                  : ""}
              </td>
            </tr>
          ))}
        </tbody>
      </Table>

      <p style={{ fontSize: 13, color: "#666" }}>
        Adding a new version below does NOT affect loans already disbursed — it only applies to
        loans disbursed on or after the effective date you choose (which can be in the future, to
        schedule an upcoming change).
      </p>
      <form onSubmit={types.submitVersion} className="form-grid">
        <input
          required
          type="number"
          step="0.0001"
          placeholder="New interest rate"
          value={newVersion.interest_rate}
          onChange={(e) => types.setVersionField("interest_rate", parseFloat(e.target.value))}
        />
        <input
          required
          type="number"
          placeholder="New tenure (months)"
          value={newVersion.tenure_months}
          onChange={(e) => types.setVersionField("tenure_months", parseInt(e.target.value))}
        />
        <input
          type="number"
          step="0.01"
          placeholder="New fee (optional)"
          value={newVersion.flat_charge}
          onChange={(e) =>
            types.setVersionField("flat_charge", parseFloat(e.target.value) || 0)
          }
        />
        <select
          aria-label="Interest deduction"
          value={newVersion.interest_mode}
          onChange={(e) =>
            types.setVersionField(
              "interest_mode",
              e.target.value as typeof newVersion.interest_mode
            )
          }
        >
          <option value="">Use the loan type's setting</option>
          {Object.entries(INTEREST_MODE_LABELS).map(([mode, label]) => (
            <option key={mode} value={mode}>
              {label}
            </option>
          ))}
        </select>
        {newVersion.interest_mode === "spread_first_months" && (
          <input
            required
            type="number"
            min={1}
            max={newVersion.tenure_months}
            placeholder="Months the interest is spread over"
            value={newVersion.interest_spread_months}
            onChange={(e) =>
              types.setVersionField(
                "interest_spread_months",
                parseInt(e.target.value) || ""
              )
            }
          />
        )}
        <input
          required
          type="date"
          value={newVersion.effective_from}
          onChange={(e) => types.setVersionField("effective_from", e.target.value)}
        />
        <div className="form-grid__full">
          <button type="submit">Add rate version</button>
        </div>
      </form>
    </div>
  );
}
