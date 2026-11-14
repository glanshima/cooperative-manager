"use client";

import LoansView from "@/components/loans/LoansView";
import { useLoansPage } from "@/components/loans/hooks/useLoansPage";
import AdminShell from "@/components/admin-shell/AdminShell";
import ModuleGate from "@/components/ui/ModuleGate";
import { userDisplayName } from "@/lib/names";
import { useAuth } from "@/lib/useAuth";

export default function LoansPage() {
  const { user, loading: authLoading, logout } = useAuth({
    requireAuth: true,
    requirePasswordChanged: true,
    requireRole: "admin",
  });

  if (authLoading) return <main style={{ padding: 32 }}>Loading...</main>;

  return (
    <AdminShell>
      <ModuleGate module="loans">
        <LoansPageContent logout={logout} identity={userDisplayName(user)} />
      </ModuleGate>
    </AdminShell>
  );
}

function LoansPageContent({
  logout,
  identity,
}: {
  logout: () => void;
  identity: string | null;
}) {
  const model = useLoansPage(false, logout);

  return <LoansView model={model} identity={identity} />;
}
