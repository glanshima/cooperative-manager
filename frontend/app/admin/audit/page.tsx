"use client";

import { useEffect, useState } from "react";
import { useAuth } from "../../../lib/useAuth";
import { listAuditEvents, AuditEvent } from "../../../lib/api";

export default function AdminAuditPage() {
  const { loading: authLoading, logout } = useAuth({
    requireAuth: true,
    requirePasswordChanged: true,
    requireRole: "admin",
  });

  const [events, setEvents] = useState<AuditEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<AuditEvent | null>(null);

  const [entityType, setEntityType] = useState("");
  const [eventType, setEventType] = useState("");

  async function refresh() {
    setLoading(true);
    setError(null);
    try {
      setEvents(
        await listAuditEvents({
          entity_type: entityType || undefined,
          event_type: eventType || undefined,
        })
      );
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (!authLoading) refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [authLoading]);

  if (authLoading) return <main style={{ padding: 32 }}>Loading...</main>;

  return (
    <main style={{ padding: 32, maxWidth: 1100, margin: "0 auto" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <h1>Audit Log</h1>
        <div style={{ display: "flex", gap: 12 }}>
          <a href="/admin/users">Users</a>
          <a href="/admin/offices">Offices</a>
          <a href="/admin/roles">Roles</a>
          <button onClick={logout}>Log out</button>
        </div>
      </div>
      <p style={{ color: "#555", fontSize: 14 }}>
        This is only reachable by staff accounts holding the <code>audit.view</code> permission -- ordinary
        members never see this page or its underlying API.
      </p>

      {error && <p style={{ color: "crimson", fontWeight: 600 }}>{error}</p>}

      <form
        onSubmit={(e) => {
          e.preventDefault();
          refresh();
        }}
        style={{ display: "flex", gap: 8, alignItems: "flex-end", marginBottom: 16 }}
      >
        <label>
          Entity type
          <input
            value={entityType}
            onChange={(e) => setEntityType(e.target.value)}
            placeholder="e.g. loan_application"
            style={{ display: "block", padding: 8 }}
          />
        </label>
        <label>
          Event type
          <input
            value={eventType}
            onChange={(e) => setEventType(e.target.value)}
            placeholder="e.g. auth.login_failed"
            style={{ display: "block", padding: 8 }}
          />
        </label>
        <button type="submit">Filter</button>
      </form>

      {loading ? (
        <p>Loading...</p>
      ) : (
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
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
            {events.map((e) => (
              <tr key={e.id} style={{ borderBottom: "1px solid #eee" }}>
                <td style={{ padding: 8, whiteSpace: "nowrap" }}>{new Date(e.timestamp).toLocaleString()}</td>
                <td style={{ padding: 8 }}>{e.actor_username || "(unknown)"}</td>
                <td style={{ padding: 8 }}>{e.event_type}</td>
                <td style={{ padding: 8 }}>
                  {e.entity_type ? `${e.entity_type}:${e.entity_id?.slice(0, 8)}` : ""}
                </td>
                <td style={{ padding: 8 }}>
                  <button onClick={() => setSelected(e)}>Details</button>
                </td>
              </tr>
            ))}
            {events.length === 0 && (
              <tr>
                <td colSpan={5} style={{ padding: 16, color: "#888" }}>
                  No audit events match this filter.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      )}

      {selected && (
        <div
          onClick={() => setSelected(null)}
          style={{
            position: "fixed",
            inset: 0,
            background: "rgba(0,0,0,0.4)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
          }}
        >
          <div
            onClick={(e) => e.stopPropagation()}
            style={{ background: "white", padding: 24, borderRadius: 8, maxWidth: 600, width: "90%" }}
          >
            <h3>{selected.event_type}</h3>
            <p>
              <strong>Actor:</strong> {selected.actor_username || "(unknown)"}{" "}
              {selected.actor_office_name && `(${selected.actor_office_name})`}
            </p>
            <p>
              <strong>Entity:</strong> {selected.entity_type} {selected.entity_id}
            </p>
            <p>
              <strong>Reason:</strong> {selected.reason || "-"}
            </p>
            <p>
              <strong>IP:</strong> {selected.ip_address || "-"}
            </p>
            {selected.previous_values && (
              <>
                <strong>Previous values</strong>
                <pre style={{ background: "#f5f5f5", padding: 8, overflow: "auto" }}>
                  {JSON.stringify(selected.previous_values, null, 2)}
                </pre>
              </>
            )}
            {selected.new_values && (
              <>
                <strong>New values</strong>
                <pre style={{ background: "#f5f5f5", padding: 8, overflow: "auto" }}>
                  {JSON.stringify(selected.new_values, null, 2)}
                </pre>
              </>
            )}
            <button onClick={() => setSelected(null)}>Close</button>
          </div>
        </div>
      )}
    </main>
  );
}
