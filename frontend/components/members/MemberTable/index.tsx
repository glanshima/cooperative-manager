import type { Member } from "@/lib/api";
import Pagination from "@/components/ui/Pagination";
import Table from "@/components/ui/Table";
import { ConflictMarker } from "@/components/ui/ConflictMarker";
import { describeMemberOption } from "../utils";

export default function MemberTable({
  members,
  loading,
  listError,
  skip,
  total,
  limit,
  onPageChange,
  onEdit,
  onDelete,
  onCreateLogin,
  onDeactivateLogin,
  onReactivateLogin,
  onWithdraw,
}: {
  members: Member[];
  loading: boolean;
  listError: string | null;
  skip: number;
  total: number;
  limit: number;
  onPageChange: (newSkip: number) => void;
  onEdit: (member: Member) => void;
  onDelete: (id: string) => void;
  onCreateLogin: (member: Member) => void;
  onDeactivateLogin: (member: Member) => void;
  onReactivateLogin: (member: Member) => void;
  onWithdraw: (member: Member) => void;
}) {
  return (
    <section>
      {loading ? (
        <p>Loading...</p>
      ) : listError ? (
        <p>Unable to load members.</p>
      ) : members.length === 0 ? (
        <p>No matching records found.</p>
      ) : (
        <>
          <Table>
            <thead>
              <tr style={{ textAlign: "left", borderBottom: "2px solid #333" }}>
                <th>PSN</th>
                <th>Name</th>
                <th>Department</th>
                <th>Status</th>
                <th>Restricted</th>
                <th>Phone</th>
                <th>Next of kin</th>
                <th>Login</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {members.map((m) => (
                <tr key={m.id} style={{ borderBottom: "1px solid #eee" }}>
                  <td>{m.psn}</td>
                  <td>{m.name}</td>
                  <td>{m.department}</td>
                  <td>
                    {m.status}
                    {/* A recorded exit is what separates a member who left
                        the cooperative from one who merely fell behind --
                        both read as non_financial without it. */}
                    {m.membership_exit_date && (
                      <div style={{ fontSize: 12, color: "#666" }}>
                        exited {m.membership_exit_date}
                      </div>
                    )}
                    {m.conflicted && (
                      <div style={{ fontSize: 12 }}>
                        <ConflictMarker />
                      </div>
                    )}
                  </td>
                  <td>{m.loan_restricted ? "⚠ yes" : ""}</td>
                  <td>{m.phone}</td>
                  <td>
                    {m.next_of_kin_is_member && m.next_of_kin_member
                      ? `${describeMemberOption(m.next_of_kin_member)} (member)`
                      : m.next_of_kin_is_member === false
                      ? m.next_of_kin || "—"
                      : "—"}
                  </td>
                  <td>{m.login_account_status ?? "no login"}</td>
                  <td>
                    {/* A conflicted member's record stays in the list --
                        this officer just isn't the one who may change it. */}
                    {m.conflicted ? (
                      <span style={{ fontSize: 13, color: "#666" }}>
                        Another officer must handle this member
                      </span>
                    ) : (
                      <>
                        <button onClick={() => onEdit(m)}>Edit</button>{" "}
                        <button onClick={() => onDelete(m.id)}>Delete</button>{" "}
                        {/* The action shown here is derived ENTIRELY from the
                            backend-computed m.login_account_status -- never
                            assumed. null/undefined means no login exists yet. */}
                        {!m.login_account_status && (
                          <button onClick={() => onCreateLogin(m)}>Create login</button>
                        )}
                        {m.login_account_status === "active" && (
                          <button onClick={() => onDeactivateLogin(m)}>Deactivate login</button>
                        )}
                        {(m.login_account_status === "deactivated" || m.login_account_status === "suspended") && (
                          <button onClick={() => onReactivateLogin(m)}>Reactivate login</button>
                        )}{" "}
                        {/* Once recorded the exit stands: it is a dated fact,
                            not a status to toggle back. */}
                        {!m.membership_exit_date && (
                          <button onClick={() => onWithdraw(m)}>Record exit</button>
                        )}
                      </>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </Table>
          <Pagination skip={skip} limit={limit} total={total} onChange={onPageChange} />
        </>
      )}
    </section>
  );
}
