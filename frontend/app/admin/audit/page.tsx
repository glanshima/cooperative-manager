"use client";

import AuditView from "@/components/audit/AuditView";
import { useAuditPage } from "@/components/audit/hooks/useAuditPage";
import AdminShell from "@/components/admin-shell/AdminShell";
import { useAuth } from "@/lib/useAuth";

export default function AdminAuditPage() {
  const { loading: authLoading, logout } = useAuth({
    requireAuth: true,
    requirePasswordChanged: true,
    requireRole: "admin",
  });
  const model = useAuditPage(authLoading, logout);

  if (authLoading) return <main style={{ padding: 32 }}>Loading...</main>;

  return (
    <AdminShell>
      <AuditView model={model} />
    </AdminShell>
  );
}
