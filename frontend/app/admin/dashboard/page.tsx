"use client";

import DashboardView from "@/components/dashboard/DashboardView";
import { useDashboardPage } from "@/components/dashboard/hooks/useDashboardPage";
import { useAuth } from "@/lib/useAuth";

export default function AdminDashboard() {
  const { user, loading: authLoading, logout } = useAuth({
    requireAuth: true,
    requirePasswordChanged: true,
    requireRole: "admin",
  });
  const model = useDashboardPage(authLoading, user, logout);

  if (authLoading || model.loading) return <main style={{ padding: 32 }}>Loading...</main>;

  return <DashboardView model={model} />;
}