"use client";

import { useEffect, useState } from "react";
import { useAuth } from "../../../lib/useAuth";
import { listRoles, createRole, updateRole, listPermissions, Role, Permission } from "../../../lib/api";

export default function AdminRolesPage() {
  const { loading: authLoading, logout } = useAuth({
    requireAuth: true,
    requirePasswordChanged: true,
    requireRole: "admin",
  });

  const [roles, setRoles] = useState<Role[]>([]);
  const [permissions, setPermissions] = useState<Permission[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [editingRoleId, setEditingRoleId] = useState<string | null>(null);
  const [editedCodes, setEditedCodes] = useState<Set<string>>(new Set());

  const [newName, setNewName] = useState("");
  const [newDescription, setNewDescription] = useState("");

  async function refresh() {
    setLoading(true);
    setError(null);
    try {
      const [r, p] = await Promise.all([listRoles(), listPermissions()]);
      setRoles(r);
      setPermissions(p);
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
      await createRole({ name: newName, description: newDescription || undefined, permission_codes: [] });
      setNewName("");
      setNewDescription("");
      await refresh();
    } catch (e: any) {
      setError(e.message);
    }
  }

  function startEdit(role: Role) {
    setEditingRoleId(role.id);
    setEditedCodes(new Set(role.permission_codes));
  }

  function toggleCode(code: string) {
    setEditedCodes((prev) => {
      const next = new Set(prev);
      if (next.has(code)) next.delete(code);
      else next.add(code);
      return next;
    });
  }

  async function saveEdit(role: Role) {
    setError(null);
    try {
      await updateRole(role.id, { permission_codes: Array.from(editedCodes) });
      setEditingRoleId(null);
      await refresh();
    } catch (e: any) {
      setError(e.message);
    }
  }

  const categories = Array.from(new Set(permissions.map((p) => p.category)));

  if (authLoading || loading) return <main style={{ padding: 32 }}>Loading...</main>;

  return (
    <main style={{ padding: 32, maxWidth: 900, margin: "0 auto" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <h1>Roles &amp; Permissions</h1>
        <div style={{ display: "flex", gap: 12 }}>
          <a href="/admin/users">Users</a>
          <a href="/admin/offices">Offices</a>
          <a href="/admin/audit">Audit log</a>
          <button onClick={logout}>Log out</button>
        </div>
      </div>
      <p style={{ color: "#555", fontSize: 14 }}>
        A Role is a reusable bundle of permissions. Assign roles to staff accounts on the Users page. The
        permission list itself comes from the approved Phase 1 catalogue; which roles hold which
        permissions is fully configurable here.
      </p>

      {error && <p style={{ color: "crimson", fontWeight: 600 }}>{error}</p>}

      <form onSubmit={handleCreate} style={{ display: "flex", gap: 8, alignItems: "flex-end", marginBottom: 24 }}>
        <label>
          Role name
          <input value={newName} onChange={(e) => setNewName(e.target.value)} required style={{ display: "block", padding: 8 }} />
        </label>
        <label>
          Description
          <input
            value={newDescription}
            onChange={(e) => setNewDescription(e.target.value)}
            style={{ display: "block", padding: 8 }}
          />
        </label>
        <button type="submit">Add role</button>
      </form>

      {roles.map((role) => (
        <section key={role.id} style={{ marginBottom: 24, border: "1px solid #ddd", borderRadius: 6, padding: 16 }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <div>
              <strong>{role.name}</strong>{" "}
              <span style={{ color: "#888" }}>{role.description}</span>
            </div>
            {editingRoleId === role.id ? (
              <div style={{ display: "flex", gap: 8 }}>
                <button onClick={() => saveEdit(role)}>Save</button>
                <button onClick={() => setEditingRoleId(null)}>Cancel</button>
              </div>
            ) : (
              <button onClick={() => startEdit(role)}>Edit permissions</button>
            )}
          </div>

          {editingRoleId === role.id ? (
            <div style={{ marginTop: 12 }}>
              {categories.map((cat) => (
                <div key={cat} style={{ marginBottom: 8 }}>
                  <div style={{ fontWeight: 600, fontSize: 13, color: "#555" }}>{cat}</div>
                  <div style={{ display: "flex", flexWrap: "wrap", gap: 12 }}>
                    {permissions
                      .filter((p) => p.category === cat)
                      .map((p) => (
                        <label key={p.code} style={{ fontSize: 13 }}>
                          <input
                            type="checkbox"
                            checked={editedCodes.has(p.code)}
                            onChange={() => toggleCode(p.code)}
                          />{" "}
                          {p.code}
                        </label>
                      ))}
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div style={{ marginTop: 8, fontSize: 13, color: "#555" }}>
              {role.permission_codes.length > 0 ? role.permission_codes.join(", ") : "No permissions granted"}
            </div>
          )}
        </section>
      ))}
    </main>
  );
}
