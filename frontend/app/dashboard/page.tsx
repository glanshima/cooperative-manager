"use client";

import DashboardView from "@/components/dashboard/DashboardView";
import { useDashboardPage } from "@/components/dashboard/hooks/useDashboardPage";
import { useAuth } from "@/lib/useAuth";

export default function MemberDashboard() {
  const { user, loading: authLoading, logout } = useAuth({
    requireAuth: true,
    requirePasswordChanged: true,
    requireRole: "member",
  });
  const model = useDashboardPage(authLoading, user, logout);

  if (authLoading || model.loading) return <main className="page">Loading...</main>;

  return <DashboardView model={model} />;
}
