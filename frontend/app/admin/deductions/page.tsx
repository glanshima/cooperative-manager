"use client";

import DeductionsView from "@/components/deductions/DeductionsView";
import { useDeductionsPage } from "@/components/deductions/hooks/useDeductionsPage";
import AdminShell from "@/components/admin-shell/AdminShell";
import ModuleGate from "@/components/ui/ModuleGate";
import { userDisplayName } from "@/lib/names";
import { useAuth } from "@/lib/useAuth";

export default function AdminDeductionsPage() {
  const { user, loading: authLoading, logout } = useAuth({
    requireAuth: true,
    requirePasswordChanged: true,
    requireRole: "admin",
  });

  if (authLoading) return <main style={{ padding: 32 }}>Loading...</main>;

  return (
    <AdminShell>
      <ModuleGate module="deductions">
        <DeductionsPageContent logout={logout} identity={userDisplayName(user)} />
      </ModuleGate>
    </AdminShell>
  );
}

function DeductionsPageContent({
  logout,
  identity,
}: {
  logout: () => void;
  identity: string | null;
}) {
  const model = useDeductionsPage(logout);

  return <DeductionsView model={model} identity={identity} />;
}
