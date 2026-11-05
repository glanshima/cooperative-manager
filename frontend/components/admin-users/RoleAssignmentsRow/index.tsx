import type { CurrentUser, Office, Role, UserRoleAssignment } from "@/lib/api";
import AssignRoleForm from "../AssignRoleForm";

export default function RoleAssignmentsRow({
  user,
  assignments,
  roles,
  offices,
  onRevoke,
  onAssign,
}: {
  user: CurrentUser;
  assignments: UserRoleAssignment[];
  roles: Role[];
  offices: Office[];
  onRevoke: (userId: string, assignmentId: string) => void;
  onAssign: (userId: string, roleId: string, officeId: string) => void;
}) {
  return (
    <tr>
      <td colSpan={6} style={{ padding: 12, background: "#fafafa" }}>
        <strong>Role assignments</strong>
        <ul style={{ marginTop: 8 }}>
          {assignments.filter((a) => a.is_active).map((a) => (
            <li key={a.id} style={{ marginBottom: 4 }}>
              {a.role_name} {a.office_name ? `(${a.office_name})` : ""}{" "}
              <button onClick={() => onRevoke(user.id, a.id)}>Revoke</button>
            </li>
          ))}
          {assignments.filter((a) => a.is_active).length === 0 && (
            <li style={{ color: "#888" }}>No active role assignments</li>
          )}
        </ul>
        <AssignRoleForm
          roles={roles}
          offices={offices}
          userIsLinked={!!user.member_id}
          onAssign={(roleId, officeId) => onAssign(user.id, roleId, officeId)}
        />
      </td>
    </tr>
  );
}
