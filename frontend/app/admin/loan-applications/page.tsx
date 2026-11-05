"use client";

import LoanApplicationsView from "@/components/loan-applications/LoanApplicationsView";
import { useLoanApplicationsPage } from "@/components/loan-applications/hooks/useLoanApplicationsPage";
import ModuleGate from "@/components/ui/ModuleGate";
import { useAuth } from "@/lib/useAuth";

export default function AdminLoanApplicationsPage() {
  const { loading: authLoading, logout } = useAuth({
    requireAuth: true,
    requirePasswordChanged: true,
    requireRole: "admin",
  });

  if (authLoading) return <main style={{ padding: 32 }}>Loading...</main>;

  return (
    <ModuleGate module="loans">
      <LoanApplicationsPageContent logout={logout} />
    </ModuleGate>
  );
}

function LoanApplicationsPageContent({ logout }: { logout: () => void }) {
  const model = useLoanApplicationsPage(false, logout);

  return <LoanApplicationsView model={model} />;
}
