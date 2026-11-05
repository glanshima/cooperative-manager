import { useState } from "react";
import type { Office, Role } from "@/lib/api";

export default function AssignRoleForm({
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
  // Client-side hint only -- the backend (admin_users.py::assign_role) is
  // the authoritative enforcement point regardless of what this UI does or
  // doesn't disable; this exists purely so the admin doesn't have to
  // submit-and-fail to discover the requirement.
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
