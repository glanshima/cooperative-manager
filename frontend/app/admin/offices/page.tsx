"use client";

import OfficesView from "@/components/offices/OfficesView";
import { useOfficesPage } from "@/components/offices/hooks/useOfficesPage";
import AdminShell from "@/components/admin-shell/AdminShell";
import { userDisplayName } from "@/lib/names";
import { useAuth } from "@/lib/useAuth";

export default function AdminOfficesPage() {
  const { user, loading: authLoading, logout } = useAuth({
    requireAuth: true,
    requirePasswordChanged: true,
    requireRole: "admin",
  });
  const model = useOfficesPage(authLoading, logout);

  if (authLoading) return <main style={{ padding: 32 }}>Loading...</main>;

  return (
    <AdminShell>
      <OfficesView model={model} identity={userDisplayName(user)} />
    </AdminShell>
  );
}
