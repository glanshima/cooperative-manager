"use client";

import { Fragment, useEffect, useRef, useState } from "react";
import { useAuth } from "../../../lib/useAuth";
import {
  listAdminUsers,
  createAdminUser,
  updateAdminUserStatus,
  updateAdminUserMemberLink,
  resetAdminUserPassword,
  listUserAssignments,
  assignRole,
  revokeRole,
  listRoles,
  listOffices,
  listMembers,
  CurrentUser,
  UserRoleAssignment,
  Role,
  Office,
  Member,
  AccountStatus,
} from "../../../lib/api";

function describeMember(m: Member): string {
  return `${m.psn} — ${m.name}`;
}

export default function AdminUsersPage() {
  const { loading: authLoading, logout } = useAuth({
    requireAuth: true,
    requirePasswordChanged: true,
    requireRole: "admin",
  });

  const [users, setUsers] = useState<CurrentUser[]>([]);
  const [roles, setRoles] = useState<Role[]>([]);
  const [offices, setOffices] = useState<Office[]>([]);
  // Map of member.id -> Member, used only to display "PSN — Name" next to
  // an admin's member_id (a plain UUID on its own isn't useful to a human).
  // Built from the existing GET /api/members endpoint -- no new backend
  // endpoint was added for this, deliberately, given how recently a
  // backend model change caused an outage; this reuses what already
  // exists, the same way loans/page.tsx already does for its own member
  // picker.
  const [memberDirectory, setMemberDirectory] = useState<Map<string, Member>>(new Map());

  const [loading, setLoading] = useState(true);

  // Error-state model (fixes the bug this remediation was largely about):
  // list-loading failures and individual-operation failures are two
  // SEPARATE states, each with its own lifecycle. Every operation clears
  // BOTH `actionError` and `success` at its own start (via beginAction()
  // below), so a stale message from operation N is never still showing
  // once operation N+1 starts -- regardless of whether N+1 is a link, an
  // unlink, a role assignment, or just an unrelated list reload.
  const [listError, setListError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const [expandedUserId, setExpandedUserId] = useState<string | null>(null);
  const [assignments, setAssignments] = useState<UserRoleAssignment[]>([]);

  const [newUsername, setNewUsername] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [newUserMemberQuery, setNewUserMemberQuery] = useState("");
  const [newUserMemberResults, setNewUserMemberResults] = useState<Member[]>([]);
  const [newUserSelectedMember, setNewUserSelectedMember] = useState<Member | null>(null);

  // Which admin's member-link dialog is currently open (link OR change --
  // same dialog either way, per the prompt's "use the existing backend
  // member-link endpoint" for both).
  const [linkDialogUserId, setLinkDialogUserId] = useState<string | null>(null);
  const [linkQuery, setLinkQuery] = useState("");
  const [linkResults, setLinkResults] = useState<Member[]>([]);
  const [linkSelectedMember, setLinkSelectedMember] = useState<Member | null>(null);

  const [resetPasswordUserId, setResetPasswordUserId] = useState<string | null>(null);
  const [tempPassword, setTempPassword] = useState("");

  // Race-safety (Section 8): every mutating operation (create, status
  // change, assign/revoke role, link/change/unlink member) shares ONE
  // sequence counter. Only the result of the MOST RECENTLY started
  // operation is ever applied to actionError/success -- so an older,
  // slow, failing request (e.g. Operation A: link to Member A, fails)
  // can never clobber a newer, faster, successful one (Operation B: link
  // to Member B, succeeds) that was started after it.
  const actionSeqRef = useRef(0);
  // Separate sequence counter for the list-loading refresh() itself, so
  // an old, slow reload can't overwrite a newer one's data either.
  const listSeqRef = useRef(0);

  function beginAction(): number {
    const seq = ++actionSeqRef.current;
    setActionError(null);
    setSuccess(null);
    return seq;
  }
  function isCurrentAction(seq: number): boolean {
    return seq === actionSeqRef.current;
  }

  async function refresh() {
    const mySeq = ++listSeqRef.current;
    setLoading(true);
    setListError(null);
    try {
      const [u, r, o, memberResult] = await Promise.all([
        listAdminUsers(),
        listRoles(),
        listOffices(),
        listMembers({ limit: 1000 }),
      ]);
      if (mySeq !== listSeqRef.current) return;
      setUsers(u);
      setRoles(r);
      setOffices(o);
      setMemberDirectory(new Map(memberResult.items.map((m) => [m.id, m])));
    } catch (e: any) {
      if (mySeq !== listSeqRef.current) return;
      setListError(e.message);
    } finally {
      if (mySeq === listSeqRef.current) setLoading(false);
    }
  }

  useEffect(() => {
    if (!authLoading) refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [authLoading]);

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    const seq = beginAction();
    try {
      const user = await createAdminUser({ username: newUsername, password: newPassword });

      // Admin creation workflow (Objective 5): linking is a SEPARATE call
      // to the SAME authoritative member-link endpoint used everywhere
      // else -- not a new/competing linkage mechanism. If this second
      // step fails, the admin account itself was still created
      // successfully; say so plainly rather than leaving an ambiguous
      // "did it work?" state.
      if (newUserSelectedMember) {
        try {
          await updateAdminUserMemberLink(user.id, newUserSelectedMember.id, "Linked at creation");
        } catch (linkErr: any) {
          if (!isCurrentAction(seq)) return;
          setActionError(
            `Admin "${user.username}" was created, but linking to ${describeMember(
              newUserSelectedMember
            )} failed: ${linkErr.message}. You can link them manually below.`
          );
          setNewUsername("");
          setNewPassword("");
          setNewUserSelectedMember(null);
          setNewUserMemberQuery("");
          setNewUserMemberResults([]);
          await refresh();
          return;
        }
      }

      if (!isCurrentAction(seq)) return;
      setSuccess(
        `Created admin "${user.username}"${
          newUserSelectedMember ? ` and linked to ${describeMember(newUserSelectedMember)}` : ""
        }.`
      );
      setNewUsername("");
      setNewPassword("");
      setNewUserSelectedMember(null);
      setNewUserMemberQuery("");
      setNewUserMemberResults([]);
      await refresh();
    } catch (e: any) {
      if (!isCurrentAction(seq)) return;
      setActionError(e.message);
    }
  }

  async function searchMembersFor(query: string, setResults: (m: Member[]) => void) {
    if (!query.trim()) {
      setResults([]);
      return;
    }
    try {
      const result = await listMembers({ search: query, limit: 10 });
      setResults(result.items);
    } catch (e: any) {
      // A failed search suggestion shouldn't blow away whatever the
      // top-level actionError is currently showing -- just show nothing.
      setResults([]);
    }
  }

  async function handleStatusChange(user: CurrentUser, status: AccountStatus) {
    const reason = window.prompt(`Reason for setting ${user.username} to ${status}? (optional)`) || undefined;
    const seq = beginAction();
    try {
      await updateAdminUserStatus(user.id, status, reason);
      if (!isCurrentAction(seq)) return;
      setSuccess(`Updated ${user.username}'s status to ${status}.`);
      await refresh();
    } catch (e: any) {
      if (!isCurrentAction(seq)) return;
      setActionError(e.message);
    }
  }

  async function toggleExpand(user: CurrentUser) {
    if (expandedUserId === user.id) {
      setExpandedUserId(null);
      return;
    }
    const seq = beginAction();
    setExpandedUserId(user.id);
    try {
      const result = await listUserAssignments(user.id);
      if (!isCurrentAction(seq)) return;
      setAssignments(result);
    } catch (e: any) {
      if (!isCurrentAction(seq)) return;
      setActionError(e.message);
    }
  }

  async function handleAssignRole(userId: string, roleId: string, officeId: string) {
    if (!roleId) return;
    const seq = beginAction();
    try {
      await assignRole(userId, roleId, officeId || undefined);
      const result = await listUserAssignments(userId);
      if (!isCurrentAction(seq)) return;
      setAssignments(result);
      setSuccess("Role assigned.");
    } catch (e: any) {
      if (!isCurrentAction(seq)) return;
      setActionError(e.message);
    }
  }

  async function handleRevoke(userId: string, assignmentId: string) {
    const seq = beginAction();
    try {
      await revokeRole(userId, assignmentId);
      const result = await listUserAssignments(userId);
      if (!isCurrentAction(seq)) return;
      setAssignments(result);
      setSuccess("Role revoked.");
    } catch (e: any) {
      if (!isCurrentAction(seq)) return;
      setActionError(e.message);
    }
  }

  async function handleAdminPasswordReset(userId: string) {
    if (!tempPassword) return;
    const seq = beginAction();
    try {
      await resetAdminUserPassword(userId, tempPassword);
      if (!isCurrentAction(seq)) return;
      setSuccess("Password reset successfully. The user must change it on next login.");
      setResetPasswordUserId(null);
      setTempPassword("");
      await refresh();
    } catch (e: any) {
      if (!isCurrentAction(seq)) return;
      setActionError(e.message);
    }
  }

  function openLinkDialog(user: CurrentUser) {
    setLinkDialogUserId(user.id);
    setLinkQuery("");
    setLinkResults([]);
    setLinkSelectedMember(null);
  }

  function closeLinkDialog() {
    setLinkDialogUserId(null);
    setLinkQuery("");
    setLinkResults([]);
    setLinkSelectedMember(null);
  }

  async function confirmLink(user: CurrentUser) {
    if (!linkSelectedMember) return;
    const seq = beginAction();
    try {
      await updateAdminUserMemberLink(
        user.id,
        linkSelectedMember.id,
        `Linked via Admin Users UI to ${describeMember(linkSelectedMember)}`
      );
      if (!isCurrentAction(seq)) return;
      setSuccess(`Linked ${user.username} to ${describeMember(linkSelectedMember)}.`);
      closeLinkDialog();
      await refresh();
    } catch (e: any) {
      if (!isCurrentAction(seq)) return;
      // Deliberately does NOT close the dialog on failure -- the admin
      // should see the error right next to the selection they just made,
      // not have it vanish along with their in-progress picks.
      setActionError(e.message);
    }
  }

  async function handleUnlink(user: CurrentUser) {
    const currentMember = user.member_id ? memberDirectory.get(user.member_id) : undefined;
    const label = currentMember ? describeMember(currentMember) : "the linked member";
    if (!window.confirm(`Unlink ${user.username} from ${label}?`)) return;
    const seq = beginAction();
    try {
      await updateAdminUserMemberLink(user.id, null, "Unlinked via Admin Users UI");
      if (!isCurrentAction(seq)) return;
      setSuccess(`Unlinked ${user.username} from ${label}.`);
      await refresh();
    } catch (e: any) {
      if (!isCurrentAction(seq)) return;
      setActionError(e.message);
    }
  }

  if (authLoading || loading) return <main style={{ padding: 32 }}>Loading...</main>;

  return (
    <main style={{ padding: 32, maxWidth: 1000, margin: "0 auto" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <h1>Staff / Admin Users</h1>
        <div style={{ display: "flex", gap: 12 }}>
          <a href="/admin/offices">Offices</a>
          <a href="/admin/roles">Roles</a>
          <a href="/admin/audit">Audit log</a>
          <button onClick={logout}>Log out</button>
        </div>
      </div>

      {actionError && (
        <p style={{ color: "crimson", fontWeight: 600, display: "flex", alignItems: "center", gap: 8 }}>
          <span>{actionError}</span>
          <button onClick={() => setActionError(null)} aria-label="Dismiss error" style={{ fontSize: 12 }}>
            Dismiss
          </button>
        </p>
      )}
      {success && <p style={{ color: "green", fontWeight: 600 }}>{success}</p>}
      {listError && <p style={{ color: "crimson", fontWeight: 600 }}>Unable to load staff accounts: {listError}</p>}

      <section style={{ marginTop: 24 }}>
        <h2>Create staff account</h2>
        <p style={{ color: "#555", fontSize: 14 }}>
          New accounts start with no permissions. Assign a Role below (with an optional Office) so the
          account can actually do anything.
        </p>
        <form onSubmit={handleCreate} style={{ display: "flex", gap: 8, alignItems: "flex-end", flexWrap: "wrap" }}>
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

        <div style={{ marginTop: 12, padding: 12, border: "1px solid #ddd", maxWidth: 480 }}>
          <strong>Optional: link to an existing Member</strong>
          <p style={{ color: "#666", fontSize: 13, margin: "4px 0" }}>
            Only needed if this staff member is also an elected officer / cooperative member (e.g. Treasurer).
            Not required otherwise.
          </p>
          {newUserSelectedMember ? (
            <p>
              Selected: <strong>{describeMember(newUserSelectedMember)}</strong>{" "}
              <button onClick={() => setNewUserSelectedMember(null)}>Clear</button>
            </p>
          ) : (
            <>
              <span style={{ display: "inline-flex", gap: 8 }}>
                <input
                  placeholder="Search member by PSN, name, or phone"
                  value={newUserMemberQuery}
                  onChange={(e) => setNewUserMemberQuery(e.target.value)}
                  onKeyDown={(e) =>
                    e.key === "Enter" && (e.preventDefault(), searchMembersFor(newUserMemberQuery, setNewUserMemberResults))
                  }
                  style={{ padding: 6, width: 260 }}
                />
                <button
                  type="button"
                  onClick={() => searchMembersFor(newUserMemberQuery, setNewUserMemberResults)}
                >
                  Search
                </button>
              </span>
              {newUserMemberResults.length > 0 && (
                <ul style={{ marginTop: 8, paddingLeft: 16 }}>
                  {newUserMemberResults.map((m) => (
                    <li key={m.id}>
                      {describeMember(m)}{" "}
                      <button type="button" onClick={() => setNewUserSelectedMember(m)}>
                        Select
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </>
          )}
        </div>
      </section>

      <section style={{ marginTop: 32 }}>
        <h2>All staff accounts</h2>
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead>
            <tr style={{ textAlign: "left", borderBottom: "1px solid #ccc" }}>
              <th style={{ padding: 8 }}>Username</th>
              <th style={{ padding: 8 }}>Status</th>
              <th style={{ padding: 8 }}>Super Admin</th>
              <th style={{ padding: 8 }}>Linked Member</th>
              <th style={{ padding: 8 }}>Last login</th>
              <th style={{ padding: 8 }}></th>
            </tr>
          </thead>
          <tbody>
            {users.map((u) => {
              const linkedMember = u.member_id ? memberDirectory.get(u.member_id) : undefined;
              return (
                <Fragment key={u.id}>
                  <tr style={{ borderBottom: "1px solid #eee" }}>
                    <td style={{ padding: 8 }}>{u.username}</td>
                    <td style={{ padding: 8 }}>{u.account_status}</td>
                    <td style={{ padding: 8 }}>{u.is_super_admin ? "Yes" : "No"}</td>
                    <td style={{ padding: 8 }}>
                      {u.member_id ? (
                        linkedMember ? (
                          describeMember(linkedMember)
                        ) : (
                          <em>Linked (member details unavailable)</em>
                        )
                      ) : (
                        <em style={{ color: "#888" }}>Not linked</em>
                      )}
                    </td>
                    <td style={{ padding: 8 }}>{u.last_login_at ? new Date(u.last_login_at).toLocaleString() : "Never"}</td>
                    <td style={{ padding: 8, display: "flex", gap: 6, flexWrap: "wrap" }}>
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
                      {u.member_id ? (
                        <>
                          <button onClick={() => openLinkDialog(u)}>Change Member</button>
                          <button onClick={() => handleUnlink(u)}>Unlink Member</button>
                        </>
                      ) : (
                        <button onClick={() => openLinkDialog(u)}>Link Member</button>
                      )}
                      <button
                        onClick={() => {
                          setResetPasswordUserId(resetPasswordUserId === u.id ? null : u.id);
                          setTempPassword("");
                        }}
                      >
                        {resetPasswordUserId === u.id ? "Cancel Reset" : "Reset Password"}
                      </button>
                    </td>
                  </tr>

                  {resetPasswordUserId === u.id && (
                    <tr>
                      <td colSpan={6} style={{ padding: 12, background: "#fafafa" }}>
                        <strong>Reset password for {u.username}</strong>
                        <p style={{ color: "#666", fontSize: 13, margin: "4px 0" }}>
                          Sets a temporary password and forces the user to choose a new password on their next login.
                        </p>
                        <form
                          onSubmit={(e) => {
                            e.preventDefault();
                            handleAdminPasswordReset(u.id);
                          }}
                          style={{ display: "flex", gap: 8, alignItems: "center", marginTop: 8 }}
                        >
                          <input
                            type="password"
                            placeholder="Temporary password (min 8 chars, 1 letter, 1 number)"
                            value={tempPassword}
                            onChange={(e) => setTempPassword(e.target.value)}
                            required
                            style={{ padding: 6, width: 320 }}
                          />
                          <button type="submit" disabled={!tempPassword}>
                            Confirm Reset
                          </button>
                          <button
                            type="button"
                            onClick={() => {
                              setResetPasswordUserId(null);
                              setTempPassword("");
                            }}
                          >
                            Cancel
                          </button>
                        </form>
                      </td>
                    </tr>
                  )}

                  {linkDialogUserId === u.id && (
                    <tr>
                      <td colSpan={6} style={{ padding: 12, background: "#fafafa" }}>
                        <strong>
                          {u.member_id ? `Change ${u.username}'s linked member` : `Link ${u.username} to a member`}
                        </strong>
                        {u.member_id && linkedMember && (
                          <p style={{ margin: "4px 0", color: "#555" }}>
                            Currently linked to: <strong>{describeMember(linkedMember)}</strong>
                          </p>
                        )}
                        {linkSelectedMember ? (
                          <p>
                            New selection: <strong>{describeMember(linkSelectedMember)}</strong>{" "}
                            <button onClick={() => setLinkSelectedMember(null)}>Change selection</button>
                          </p>
                        ) : (
                          <>
                            <span style={{ display: "inline-flex", gap: 8, marginTop: 8 }}>
                              <input
                                placeholder="Search member by PSN, name, or phone"
                                value={linkQuery}
                                onChange={(e) => setLinkQuery(e.target.value)}
                                onKeyDown={(e) =>
                                  e.key === "Enter" && (e.preventDefault(), searchMembersFor(linkQuery, setLinkResults))
                                }
                                style={{ padding: 6, width: 260 }}
                              />
                              <button onClick={() => searchMembersFor(linkQuery, setLinkResults)}>Search</button>
                            </span>
                            {linkResults.length > 0 && (
                              <ul style={{ marginTop: 8, paddingLeft: 16 }}>
                                {linkResults.map((m) => (
                                  <li key={m.id}>
                                    {describeMember(m)}{" "}
                                    <button onClick={() => setLinkSelectedMember(m)}>Select</button>
                                  </li>
                                ))}
                              </ul>
                            )}
                          </>
                        )}
                        <div style={{ marginTop: 12, display: "flex", gap: 8 }}>
                          <button onClick={() => confirmLink(u)} disabled={!linkSelectedMember}>
                            Confirm {u.member_id ? "change" : "link"}
                          </button>
                          <button onClick={closeLinkDialog}>Cancel</button>
                        </div>
                      </td>
                    </tr>
                  )}

                  {expandedUserId === u.id && (
                    <tr>
                      <td colSpan={6} style={{ padding: 12, background: "#fafafa" }}>
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
                          userIsLinked={!!u.member_id}
                          onAssign={(roleId, officeId) => handleAssignRole(u.id, roleId, officeId)}
                        />
                      </td>
                    </tr>
                  )}
                </Fragment>
              );
            })}
          </tbody>
        </table>
      </section>
    </main>
  );
}

function AssignRoleForm({
  roles,
  offices,
  userIsLinked,
  onAssign,
}: {
  roles: Role[];
  offices: Office[];
  userIsLinked: boolean;
  onAssign: (roleId: string, officeId: string) => void;
}) {
  const [roleId, setRoleId] = useState("");
  const [officeId, setOfficeId] = useState("");

  const selectedRole = roles.find((r) => r.id === roleId);
  // Client-side hint only -- the backend (admin_users.py::assign_role)
  // is the authoritative enforcement point regardless of what this UI
  // does or doesn't disable; this exists purely so the admin doesn't
  // have to submit-and-fail to discover the requirement.
  const blockedByMissingLink = !!selectedRole?.requires_member_link && !userIsLinked;

  return (
    <div style={{ marginTop: 12 }}>
      <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
        <select value={roleId} onChange={(e) => setRoleId(e.target.value)}>
          <option value="">Select a role...</option>
          {roles.map((r) => (
            <option key={r.id} value={r.id}>
              {r.name}
              {r.requires_member_link ? " (requires Member link)" : ""}
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
          disabled={!roleId || blockedByMissingLink}
        >
          Assign
        </button>
      </div>
      {blockedByMissingLink && (
        <p style={{ color: "#a15c00", fontSize: 13, marginTop: 4 }}>
          This role requires the account to be linked to a Member first -- use "Link Member" above
          before assigning it.
        </p>
      )}
    </div>
  );
}
