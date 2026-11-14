"use client";

import AdminUsersView from "@/components/admin-users/AdminUsersView";
import { useAdminUsersPage } from "@/components/admin-users/hooks/useAdminUsersPage";
import AdminShell from "@/components/admin-shell/AdminShell";
import { userDisplayName } from "@/lib/names";
import { useAuth } from "@/lib/useAuth";

export default function AdminUsersPage() {
  const { user, loading, logout } = useAuth({
    requireAuth: true,
    requirePasswordChanged: true,
    requireRole: "admin",
  });
  const model = useAdminUsersPage(loading, logout);

  if (loading || model.loading) return <main style={{ padding: 32 }}>Loading...</main>;

  return (
    <AdminShell>
      <AdminUsersView model={model} identity={userDisplayName(user)} />
    </AdminShell>
  );
}
