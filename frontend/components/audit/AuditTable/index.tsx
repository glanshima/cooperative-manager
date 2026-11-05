import Table from "@/components/ui/Table";
import type { AuditPageModel } from "../hooks/useAuditPage";

export default function AuditTable({ table }: { table: AuditPageModel["table"] }) {
  if (table.loading) return <p>Loading...</p>;

  return (
    <Table>
      <thead>
        <tr style={{ textAlign: "left", borderBottom: "1px solid #ccc" }}>
          <th style={{ padding: 8 }}>Time</th>
          <th style={{ padding: 8 }}>Actor</th>
          <th style={{ padding: 8 }}>Event</th>
          <th style={{ padding: 8 }}>Entity</th>
          <th style={{ padding: 8 }}></th>
        </tr>
      </thead>
      <tbody>
        {table.items.map((e) => (
          <tr key={e.id} style={{ borderBottom: "1px solid #eee" }}>
            <td style={{ padding: 8, whiteSpace: "nowrap" }}>
              {new Date(e.timestamp).toLocaleString()}
            </td>
            <td style={{ padding: 8 }}>{e.actor_username || "(unknown)"}</td>
            <td style={{ padding: 8 }}>{e.event_type}</td>
            <td style={{ padding: 8 }}>
              {e.entity_type ? `${e.entity_type}:${e.entity_id?.slice(0, 8)}` : ""}
            </td>
            <td style={{ padding: 8 }}>
              <button onClick={() => table.onDetails(e)}>Details</button>
            </td>
          </tr>
        ))}
        {table.items.length === 0 && (
          <tr>
            <td colSpan={5} style={{ padding: 16, color: "#888" }}>
              No audit events match this filter.
            </td>
          </tr>
        )}
      </tbody>
    </Table>
  );
}
