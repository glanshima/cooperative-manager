import { Fragment } from "react";
import Table from "@/components/ui/Table";
import type { AdminUsersPageModel } from "../hooks/useAdminUsersPage";
import LinkMemberRow from "../LinkMemberRow";
import ResetPasswordRow from "../ResetPasswordRow";
import RoleAssignmentsRow from "../RoleAssignmentsRow";
import { describeMember } from "../utils";

export default function StaffTable({ table }: { table: AdminUsersPageModel["table"] }) {
  const { users, roles, offices, memberDirectory, expandedUserId, assignments, link, reset } = table;

  return (
    <section style={{ marginTop: 32 }}>
      <h2>All staff accounts</h2>
      <Table>
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
                  <td style={{ padding: 8 }}>
                    {u.last_login_at ? new Date(u.last_login_at).toLocaleString() : "Never"}
                  </td>
                  <td style={{ padding: 8, display: "flex", gap: 6, flexWrap: "wrap" }}>
                    <button onClick={() => table.onToggleExpand(u)}>
                      {expandedUserId === u.id ? "Hide roles" : "Roles"}
                    </button>
                    {u.account_status === "active" ? (
                      <button onClick={() => table.onStatusChange(u, "suspended")}>Suspend</button>
                    ) : (
                      <button onClick={() => table.onStatusChange(u, "active")}>Reactivate</button>
                    )}
                    {u.account_status !== "deactivated" && (
                      <button onClick={() => table.onStatusChange(u, "deactivated")}>Deactivate</button>
                    )}
                    {u.member_id ? (
                      <>
                        <button onClick={() => link.open(u)}>Change Member</button>
                        <button onClick={() => table.onUnlink(u)}>Unlink Member</button>
                      </>
                    ) : (
                      <button onClick={() => link.open(u)}>Link Member</button>
                    )}
                    <button onClick={() => reset.toggle(u.id)}>
                      {reset.userId === u.id ? "Cancel Reset" : "Reset Password"}
                    </button>
                  </td>
                </tr>

                {reset.userId === u.id && (
                  <ResetPasswordRow
                    user={u}
                    tempPassword={reset.tempPassword}
                    onTempPasswordChange={reset.setTempPassword}
                    onConfirm={reset.confirm}
                    onCancel={reset.cancel}
                  />
                )}

                {link.dialogUserId === u.id && (
                  <LinkMemberRow user={u} linkedMember={linkedMember} link={link} />
                )}

                {expandedUserId === u.id && (
                  <RoleAssignmentsRow
                    user={u}
                    assignments={assignments}
                    roles={roles}
                    offices={offices}
                    onRevoke={table.onRoleRevoke}
                    onAssign={table.onRoleAssign}
                  />
                )}
              </Fragment>
            );
          })}
        </tbody>
      </Table>
    </section>
  );
}
