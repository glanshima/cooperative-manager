import type { OfficesPageModel } from "../hooks/useOfficesPage";

export default function OfficesTable({ table }: { table: OfficesPageModel["table"] }) {
  return (
    <table style={{ width: "100%", borderCollapse: "collapse" }}>
      <thead>
        <tr style={{ textAlign: "left", borderBottom: "1px solid #ccc" }}>
          <th style={{ padding: 8 }}>Name</th>
          <th style={{ padding: 8 }}>Description</th>
          <th style={{ padding: 8 }}>Active</th>
          <th style={{ padding: 8 }}></th>
        </tr>
      </thead>
      <tbody>
        {table.items.map((o) => (
          <tr key={o.id} style={{ borderBottom: "1px solid #eee" }}>
            <td style={{ padding: 8 }}>{o.name}</td>
            <td style={{ padding: 8 }}>{o.description}</td>
            <td style={{ padding: 8 }}>{o.is_active ? "Yes" : "No"}</td>
            <td style={{ padding: 8 }}>
              <button onClick={() => table.onToggleActive(o)}>
                {o.is_active ? "Deactivate" : "Reactivate"}
              </button>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
