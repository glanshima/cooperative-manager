import Table from "@/components/ui/Table";
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
      <h4>
        Rate history — {historyFor.name} <button onClick={types.closeHistory}>Close</button>
      </h4>
      <Table style={{ marginBottom: 12 }}>
        <thead>
          <tr style={{ textAlign: "left", borderBottom: "1px solid #ccc" }}>
            <th>Effective from</th>
            <th>Rate</th>
            <th>Tenure</th>
            <th>Flat charge</th>
          </tr>
        </thead>
        <tbody>
          {history.map((v) => (
            <tr key={v.id}>
              <td>{v.effective_from}</td>
              <td>{(parseFloat(v.interest_rate) * 100).toFixed(2)}%</td>
              <td>{v.tenure_months}mo</td>
              <td>{v.flat_charge}</td>
            </tr>
          ))}
        </tbody>
      </Table>

      <p style={{ fontSize: 13, color: "#666" }}>
        Adding a new version below does NOT affect loans already disbursed — it only applies to
        loans disbursed on or after the effective date you choose (which can be in the future, to
        schedule an upcoming change).
      </p>
      <form
        onSubmit={types.submitVersion}
        style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}
      >
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
          placeholder="New flat charge"
          value={newVersion.flat_charge}
          onChange={(e) =>
            types.setVersionField("flat_charge", parseFloat(e.target.value) || 0)
          }
        />
        <input
          required
          type="date"
          value={newVersion.effective_from}
          onChange={(e) => types.setVersionField("effective_from", e.target.value)}
        />
        <div style={{ gridColumn: "1 / -1" }}>
          <button type="submit">Add rate version</button>
        </div>
      </form>
    </div>
  );
}
