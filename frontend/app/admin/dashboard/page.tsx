"use client";

import AdminDashboardView from "@/components/admin-dashboard/AdminDashboardView";
import { useAdminDashboardPage } from "@/components/admin-dashboard/hooks/useAdminDashboardPage";
import AdminShell from "@/components/admin-shell/AdminShell";
import { useAuth } from "@/lib/useAuth";

export default function AdminDashboard() {
  const { user, loading: authLoading, logout } = useAuth({
    requireAuth: true,
    requirePasswordChanged: true,
    requireRole: "admin",
  });
  const model = useAdminDashboardPage(authLoading, user, logout);

  if (authLoading || model.loading) return <main style={{ padding: 32 }}>Loading...</main>;

  return (
    <AdminShell>
      <AdminDashboardView model={model} />
    </AdminShell>
  );
}
