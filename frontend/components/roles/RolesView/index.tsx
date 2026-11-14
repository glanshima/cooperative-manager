import StatusMessage from "@/components/ui/StatusMessage";
import LogoutControl from "@/components/ui/LogoutControl";
import type { RolesPageModel } from "../hooks/useRolesPage";
import CreateRoleForm from "../CreateRoleForm";
import RoleEditor from "../RoleEditor";

export default function RolesView({
  model,
  identity,
}: {
  model: RolesPageModel;
  identity?: string | null;
}) {
  if (model.loading) {
    return <main className="page">Loading...</main>;
  }

  return (
    <main className="page page--900">
      <div className="page-header">
        <h1>Roles &amp; Permissions</h1>
        <div className="toolbar">
          <a href="/admin/users">Users</a>
          <a href="/admin/offices">Offices</a>
          <a href="/admin/audit">Audit log</a>
          <LogoutControl identity={identity} onLogout={model.auth.logout} />
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
