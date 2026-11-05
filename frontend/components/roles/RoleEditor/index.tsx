import type { Role } from "@/lib/api";
import type { RolesPageModel } from "../hooks/useRolesPage";

export default function RoleEditor({
  role,
  permissions,
  categories,
  edit,
}: {
  role: Role;
  permissions: RolesPageModel["list"]["permissions"];
  categories: string[];
  edit: RolesPageModel["edit"];
}) {
  const editing = edit.roleId === role.id;

  return (
    <section style={{ marginBottom: 24, border: "1px solid #ddd", borderRadius: 6, padding: 16 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <div>
          <strong>{role.name}</strong>{" "}
          <span style={{ color: "#888" }}>{role.description}</span>
          {role.requires_member_link && (
            <span
              style={{
                marginLeft: 8,
                fontSize: 11,
                padding: "2px 6px",
                borderRadius: 4,
                background: "#fff3cd",
                color: "#664d03",
              }}
              title="An account must be linked to a Member before this role can be assigned to it."
            >
              Requires Member link
            </span>
          )}
        </div>
        {editing ? (
          <div style={{ display: "flex", gap: 8 }}>
            <button onClick={() => edit.save(role)}>Save</button>
            <button onClick={edit.cancel}>Cancel</button>
          </div>
        ) : (
          <button onClick={() => edit.start(role)}>Edit permissions</button>
        )}
      </div>

      {editing ? (
        <div style={{ marginTop: 12 }}>
          <label style={{ display: "block", marginBottom: 12, fontSize: 13 }}>
            <input
              type="checkbox"
              checked={edit.requiresMemberLink}
              onChange={(e) => edit.setRequiresMemberLink(e.target.checked)}
            />{" "}
            Requires Member link (an account must be linked to a Member before this role can be
            assigned, and cannot be unlinked from its Member while holding this role)
          </label>
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
                        checked={edit.codes.has(p.code)}
                        onChange={() => edit.toggleCode(p.code)}
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
          {role.permission_codes.length > 0
            ? role.permission_codes.join(", ")
            : "No permissions granted"}
        </div>
      )}
    </section>
  );
}
