import type { Member } from "@/lib/api";
import Pagination from "@/components/ui/Pagination";
import Table from "@/components/ui/Table";
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
                  <td>{m.status}</td>
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
