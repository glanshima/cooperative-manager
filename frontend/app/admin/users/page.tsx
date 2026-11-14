"use client";

import AdminUsersView from "@/components/admin-users/AdminUsersView";
import { useAdminUsersPage } from "@/components/admin-users/hooks/useAdminUsersPage";
import AdminShell from "@/components/admin-shell/AdminShell";
import { useAuth } from "@/lib/useAuth";

export default function AdminUsersPage() {
  const { loading, logout } = useAuth({
    requireAuth: true,
    requirePasswordChanged: true,
    requireRole: "admin",
  });
  const model = useAdminUsersPage(loading, logout);

  if (loading || model.loading) return <main style={{ padding: 32 }}>Loading...</main>;

  return (
    <AdminShell>
      <AdminUsersView model={model} />
    </AdminShell>
  );
}
