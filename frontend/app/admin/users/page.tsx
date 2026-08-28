"use client";

import { Fragment, useEffect, useState } from "react";
import { useAuth } from "../../../lib/useAuth";
import {
  listAdminUsers,
  createAdminUser,
  updateAdminUserStatus,
  listUserAssignments,
  assignRole,
  revokeRole,
  listRoles,
  listOffices,
  CurrentUser,
  UserRoleAssignment,
  Role,
  Office,
  AccountStatus,
} from "../../../lib/api";

export default function AdminUsersPage() {
  const { loading: authLoading, logout } = useAuth({
    requireAuth: true,
    requirePasswordChanged: true,
    requireRole: "admin",
  });

  const [users, setUsers] = useState<CurrentUser[]>([]);
  const [roles, setRoles] = useState<Role[]>([]);
  const [offices, setOffices] = useState<Office[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [expandedUserId, setExpandedUserId] = useState<string | null>(null);
  const [assignments, setAssignments] = useState<UserRoleAssignment[]>([]);

  const [newUsername, setNewUsername] = useState("");
  const [newPassword, setNewPassword] = useState("");

  async function refresh() {
    setLoading(true);
    setError(null);
    try {
      const [u, r, o] = await Promise.all([listAdminUsers(), listRoles(), listOffices()]);
      setUsers(u);
      setRoles(r);
      setOffices(o);
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
      await createAdminUser({ username: newUsername, password: newPassword });
      setNewUsername("");
      setNewPassword("");
      await refresh();
    } catch (e: any) {
      setError(e.message);
    }
  }

  async function handleStatusChange(user: CurrentUser, status: AccountStatus) {
    const reason = window.prompt(`Reason for setting ${user.username} to ${status}? (optional)`) || undefined;
    setError(null);
    try {
      await updateAdminUserStatus(user.id, status, reason);
      await refresh();
    } catch (e: any) {
      setError(e.message);
    }
  }

  async function toggleExpand(user: CurrentUser) {
    if (expandedUserId === user.id) {
      setExpandedUserId(null);
      return;
    }
    setExpandedUserId(user.id);
    try {
      setAssignments(await listUserAssignments(user.id));
    } catch (e: any) {
      setError(e.message);
    }
  }

  async function handleAssignRole(userId: string, roleId: string, officeId: string) {
    if (!roleId) return;
    setError(null);
    try {
      await assignRole(userId, roleId, officeId || undefined);
      setAssignments(await listUserAssignments(userId));
    } catch (e: any) {
      setError(e.message);
    }
  }

  async function handleRevoke(userId: string, assignmentId: string) {
    setError(null);
    try {
      await revokeRole(userId, assignmentId);
      setAssignments(await listUserAssignments(userId));
    } catch (e: any) {
      setError(e.message);
    }
  }

  if (authLoading || loading) return <main style={{ padding: 32 }}>Loading...</main>;

  return (
    <main style={{ padding: 32, maxWidth: 900, margin: "0 auto" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <h1>Staff / Admin Users</h1>
        <div style={{ display: "flex", gap: 12 }}>
          <a href="/admin/offices">Offices</a>
          <a href="/admin/roles">Roles</a>
          <a href="/admin/audit">Audit log</a>
          <button onClick={logout}>Log out</button>
        </div>
      </div>

      {error && <p style={{ color: "crimson", fontWeight: 600 }}>{error}</p>}

      <section style={{ marginTop: 24 }}>
        <h2>Create staff account</h2>
        <p style={{ color: "#555", fontSize: 14 }}>
          New accounts start with no permissions. Assign a Role below (with an optional Office) so the
          account can actually do anything.
        </p>
        <form onSubmit={handleCreate} style={{ display: "flex", gap: 8, alignItems: "flex-end" }}>
          <label>
            Username
            <input
              value={newUsername}
              onChange={(e) => setNewUsername(e.target.value)}
              required
              style={{ display: "block", padding: 8 }}
            />
          </label>
          <label>
            Temporary password
            <input
              type="password"
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              required
              style={{ display: "block", padding: 8 }}
            />
          </label>
          <button type="submit">Create</button>
        </form>
      </section>

      <section style={{ marginTop: 32 }}>
        <h2>All staff accounts</h2>
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead>
            <tr style={{ textAlign: "left", borderBottom: "1px solid #ccc" }}>
              <th style={{ padding: 8 }}>Username</th>
              <th style={{ padding: 8 }}>Status</th>
              <th style={{ padding: 8 }}>Super Admin</th>
              <th style={{ padding: 8 }}>Last login</th>
              <th style={{ padding: 8 }}></th>
            </tr>
          </thead>
          <tbody>
            {users.map((u) => (
              <Fragment key={u.id}>
                <tr key={u.id} style={{ borderBottom: "1px solid #eee" }}>
                  <td style={{ padding: 8 }}>{u.username}</td>
                  <td style={{ padding: 8 }}>{u.account_status}</td>
                  <td style={{ padding: 8 }}>{u.is_super_admin ? "Yes" : "No"}</td>
                  <td style={{ padding: 8 }}>{u.last_login_at ? new Date(u.last_login_at).toLocaleString() : "Never"}</td>
                  <td style={{ padding: 8, display: "flex", gap: 6 }}>
                    <button onClick={() => toggleExpand(u)}>
                      {expandedUserId === u.id ? "Hide roles" : "Roles"}
                    </button>
                    {u.account_status === "active" ? (
                      <button onClick={() => handleStatusChange(u, "suspended")}>Suspend</button>
                    ) : (
                      <button onClick={() => handleStatusChange(u, "active")}>Reactivate</button>
                    )}
                    {u.account_status !== "deactivated" && (
                      <button onClick={() => handleStatusChange(u, "deactivated")}>Deactivate</button>
                    )}
                  </td>
                </tr>
                {expandedUserId === u.id && (
                  <tr>
                    <td colSpan={5} style={{ padding: 12, background: "#fafafa" }}>
                      <strong>Role assignments</strong>
                      <ul style={{ marginTop: 8 }}>
                        {assignments.filter((a) => a.is_active).map((a) => (
                          <li key={a.id} style={{ marginBottom: 4 }}>
                            {a.role_name} {a.office_name ? `(${a.office_name})` : ""}{" "}
                            <button onClick={() => handleRevoke(u.id, a.id)}>Revoke</button>
                          </li>
                        ))}
                        {assignments.filter((a) => a.is_active).length === 0 && (
                          <li style={{ color: "#888" }}>No active role assignments</li>
                        )}
                      </ul>
                      <AssignRoleForm
                        roles={roles}
                        offices={offices}
                        onAssign={(roleId, officeId) => handleAssignRole(u.id, roleId, officeId)}
                      />
                    </td>
                  </tr>
                )}
              </Fragment>
            ))}
          </tbody>
        </table>
      </section>
    </main>
  );
}

function AssignRoleForm({
  roles,
  offices,
  onAssign,
}: {
  roles: Role[];
  offices: Office[];
  onAssign: (roleId: string, officeId: string) => void;
}) {
  const [roleId, setRoleId] = useState("");
  const [officeId, setOfficeId] = useState("");

  return (
    <div style={{ marginTop: 12, display: "flex", gap: 8, alignItems: "center" }}>
      <select value={roleId} onChange={(e) => setRoleId(e.target.value)}>
        <option value="">Select a role...</option>
        {roles.map((r) => (
          <option key={r.id} value={r.id}>
            {r.name}
          </option>
        ))}
      </select>
      <select value={officeId} onChange={(e) => setOfficeId(e.target.value)}>
        <option value="">(no office)</option>
        {offices.map((o) => (
          <option key={o.id} value={o.id}>
            {o.name}
          </option>
        ))}
      </select>
      <button
        onClick={() => {
          onAssign(roleId, officeId);
          setRoleId("");
          setOfficeId("");
        }}
        disabled={!roleId}
      >
        Assign
      </button>
    </div>
  );
}
