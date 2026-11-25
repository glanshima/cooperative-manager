"use client";

import AdminDashboardView from "@/components/admin-dashboard/AdminDashboardView";
import { useAdminDashboardPage } from "@/components/admin-dashboard/hooks/useAdminDashboardPage";
import PageSkeleton from "@/components/ui/PageSkeleton";
import { useAuth } from "@/lib/useAuth";

export default function AdminDashboard() {
  const { user, loading: authLoading } = useAuth({
    requireAuth: true,
    requirePasswordChanged: true,
    requireRole: "admin",
  });
  const model = useAdminDashboardPage(authLoading, user);

  if (authLoading || model.loading) return <PageSkeleton />;

  return <AdminDashboardView model={model} />;
}
