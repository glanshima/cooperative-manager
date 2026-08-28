"use client";

import { useEffect, useState } from "react";
import { useAuth } from "../../../lib/useAuth";
import { listOffices, createOffice, updateOffice, Office } from "../../../lib/api";

export default function AdminOfficesPage() {
  const { loading: authLoading, logout } = useAuth({
    requireAuth: true,
    requirePasswordChanged: true,
    requireRole: "admin",
  });

  const [offices, setOffices] = useState<Office[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");

  async function refresh() {
    setLoading(true);
    setError(null);
    try {
      setOffices(await listOffices());
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

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      await createOffice({ name, description: description || undefined });
      setName("");
      setDescription("");
      await refresh();
    } catch (e: any) {
      setError(e.message);
    }
  }

  async function toggleActive(office: Office) {
    setError(null);
    try {
      await updateOffice(office.id, { is_active: !office.is_active });
      await refresh();
    } catch (e: any) {
      setError(e.message);
    }
  }

  if (authLoading || loading) return <main style={{ padding: 32 }}>Loading...</main>;

  return (
    <main style={{ padding: 32, maxWidth: 700, margin: "0 auto" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <h1>Offices</h1>
        <div style={{ display: "flex", gap: 12 }}>
          <a href="/admin/users">Users</a>
          <a href="/admin/roles">Roles</a>
          <a href="/admin/audit">Audit log</a>
          <button onClick={logout}>Log out</button>
        </div>
      </div>
      <p style={{ color: "#555", fontSize: 14 }}>
        Offices are a title/accountability grouping (President, Treasurer, ...). Add as many as your
        cooperative uses -- no code change is needed. Authorization itself comes from the Role you assign
        alongside an office, not the office name itself.
      </p>

      {error && <p style={{ color: "crimson", fontWeight: 600 }}>{error}</p>}

      <form onSubmit={handleCreate} style={{ display: "flex", gap: 8, alignItems: "flex-end", marginBottom: 24 }}>
        <label>
          Name
          <input value={name} onChange={(e) => setName(e.target.value)} required style={{ display: "block", padding: 8 }} />
        </label>
        <label>
          Description
          <input
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            style={{ display: "block", padding: 8 }}
          />
        </label>
        <button type="submit">Add office</button>
      </form>

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
          {offices.map((o) => (
            <tr key={o.id} style={{ borderBottom: "1px solid #eee" }}>
              <td style={{ padding: 8 }}>{o.name}</td>
              <td style={{ padding: 8 }}>{o.description}</td>
              <td style={{ padding: 8 }}>{o.is_active ? "Yes" : "No"}</td>
              <td style={{ padding: 8 }}>
                <button onClick={() => toggleActive(o)}>{o.is_active ? "Deactivate" : "Reactivate"}</button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </main>
  );
}
