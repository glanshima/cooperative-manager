"use client";

import SettingsView from "@/components/admin-settings/SettingsView";
import { useSettingsPage } from "@/components/admin-settings/hooks/useSettingsPage";
import AdminShell from "@/components/admin-shell/AdminShell";
import { useAuth } from "@/lib/useAuth";

export default function AdminSettingsPage() {
  const { loading: authLoading, logout } = useAuth({
    requireAuth: true,
    requirePasswordChanged: true,
    requireRole: "admin",
  });
  const model = useSettingsPage(authLoading, logout);

  if (authLoading) return <main style={{ padding: 32 }}>Loading...</main>;

  return (
    <AdminShell>
      <SettingsView model={model} />
    </AdminShell>
  );
}
