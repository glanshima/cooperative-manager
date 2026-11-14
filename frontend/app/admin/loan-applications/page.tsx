"use client";

import LoanApplicationsView from "@/components/loan-applications/LoanApplicationsView";
import { useLoanApplicationsPage } from "@/components/loan-applications/hooks/useLoanApplicationsPage";
import AdminShell from "@/components/admin-shell/AdminShell";
import ModuleGate from "@/components/ui/ModuleGate";
import { userDisplayName } from "@/lib/names";
import { useAuth } from "@/lib/useAuth";

export default function AdminLoanApplicationsPage() {
  const { user, loading: authLoading, logout } = useAuth({
    requireAuth: true,
    requirePasswordChanged: true,
    requireRole: "admin",
  });

  if (authLoading) return <main style={{ padding: 32 }}>Loading...</main>;

  return (
    <AdminShell>
      <ModuleGate module="loans">
        <LoanApplicationsPageContent logout={logout} identity={userDisplayName(user)} />
      </ModuleGate>
    </AdminShell>
  );
}

function LoanApplicationsPageContent({
  logout,
  identity,
}: {
  logout: () => void;
  identity: string | null;
}) {
  const model = useLoanApplicationsPage(false, logout);

  return <LoanApplicationsView model={model} identity={identity} />;
}
