import StatusMessage from "@/components/ui/StatusMessage";
import type { RolesPageModel } from "../hooks/useRolesPage";
import CreateRoleForm from "../CreateRoleForm";
import RoleEditor from "../RoleEditor";

export default function RolesView({ model }: { model: RolesPageModel }) {
  if (model.loading) {
    return <main style={{ padding: 32 }}>Loading...</main>;
  }

  return (
    <main style={{ padding: 32, maxWidth: 900, margin: "0 auto" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <h1>Roles &amp; Permissions</h1>
        <div style={{ display: "flex", gap: 12 }}>
          <a href="/admin/users">Users</a>
          <a href="/admin/offices">Offices</a>
          <a href="/admin/audit">Audit log</a>
          <button onClick={model.auth.logout}>Log out</button>
        </div>
      </div>
      <p style={{ color: "#555", fontSize: 14 }}>
        A Role is a reusable bundle of permissions. Assign roles to staff accounts on the Users page. The
        permission list itself comes from the approved Phase 1 catalogue; which roles hold which
        permissions is fully configurable here.
      </p>

      {model.feedback.error && (
        <StatusMessage tone="error">{model.feedback.error}</StatusMessage>
      )}

      <CreateRoleForm create={model.create} />

      {model.list.items.map((role) => (
        <RoleEditor
          key={role.id}
          role={role}
          permissions={model.list.permissions}
          categories={model.list.categories}
          edit={model.edit}
        />
      ))}
    </main>
  );
}
