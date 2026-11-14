"use client";

import DisbursementsView from "@/components/disbursements/DisbursementsView";
import { useDisbursementsPage } from "@/components/disbursements/hooks/useDisbursementsPage";
import AdminShell from "@/components/admin-shell/AdminShell";
import ModuleGate from "@/components/ui/ModuleGate";
import { userDisplayName } from "@/lib/names";
import { useAuth } from "@/lib/useAuth";

export default function AdminDisbursementsPage() {
  const { user, loading: authLoading, logout } = useAuth({
    requireAuth: true,
    requirePasswordChanged: true,
    requireRole: "admin",
  });

  if (authLoading) return <main style={{ padding: 32 }}>Loading...</main>;

  return (
    <AdminShell>
      <ModuleGate module="loans">
        <DisbursementsPageContent logout={logout} identity={userDisplayName(user)} />
      </ModuleGate>
    </AdminShell>
  );
}

function DisbursementsPageContent({
  logout,
  identity,
}: {
  logout: () => void;
  identity: string | null;
}) {
  const model = useDisbursementsPage(false, logout);

  return <DisbursementsView model={model} identity={identity} />;
}
