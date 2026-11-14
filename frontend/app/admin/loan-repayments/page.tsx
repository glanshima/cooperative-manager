"use client";

import LoanRepaymentsView from "@/components/loan-repayments/LoanRepaymentsView";
import { useLoanRepaymentsPage } from "@/components/loan-repayments/hooks/useLoanRepaymentsPage";
import AdminShell from "@/components/admin-shell/AdminShell";
import ModuleGate from "@/components/ui/ModuleGate";
import { userDisplayName } from "@/lib/names";
import { useAuth } from "@/lib/useAuth";

export default function AdminLoanRepaymentsPage() {
  const { user, loading: authLoading, logout } = useAuth({
    requireAuth: true,
    requirePasswordChanged: true,
    requireRole: "admin",
  });

  if (authLoading) return <main style={{ padding: 32 }}>Loading...</main>;

  return (
    <AdminShell>
      <ModuleGate module="loans">
        <LoanRepaymentsPageContent logout={logout} identity={userDisplayName(user)} />
      </ModuleGate>
    </AdminShell>
  );
}

function LoanRepaymentsPageContent({
  logout,
  identity,
}: {
  logout: () => void;
  identity: string | null;
}) {
  const model = useLoanRepaymentsPage(false, logout);

  return <LoanRepaymentsView model={model} identity={identity} />;
}
