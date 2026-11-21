"use client";

import SettingsView from "@/components/admin-settings/SettingsView";
import { useSettingsPage } from "@/components/admin-settings/hooks/useSettingsPage";
import PageSkeleton from "@/components/ui/PageSkeleton";
import { useAuth } from "@/lib/useAuth";

export default function AdminSettingsPage() {
  const { user, loading: authLoading, logout } = useAuth({
    requireAuth: true,
    requirePasswordChanged: true,
    requireRole: "admin",
  });
  const model = useSettingsPage(authLoading, logout);

  if (authLoading) return <PageSkeleton />;

  return (
    <SettingsView model={model} permissions={user?.permissions ?? []} />
  );
}
