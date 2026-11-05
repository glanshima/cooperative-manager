import Table from "@/components/ui/Table";
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
      <Table style={{ marginBottom: 16 }}>
        <thead>
          <tr style={{ textAlign: "left", borderBottom: "2px solid #333" }}>
            <th>Name</th>
            <th>Description</th>
            <th>Rate</th>
            <th>Tenure (months)</th>
            <th>Flat charge</th>
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
      <form
        onSubmit={types.submit}
        style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}
      >
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
        <input
          type="number"
          step="0.01"
          placeholder="Flat charge (optional, e.g. 500)"
          value={form.flat_charge}
          onChange={(e) => types.setField("flat_charge", parseFloat(e.target.value) || 0)}
        />
        <input
          required
          type="date"
          value={form.effective_from}
          onChange={(e) => types.setField("effective_from", e.target.value)}
        />
        <div style={{ gridColumn: "1 / -1" }}>
          <button type="submit">Add loan type</button>
        </div>
      </form>
    </section>
  );
}
