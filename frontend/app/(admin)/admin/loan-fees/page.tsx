"use client";

import LoanFeesView from "@/components/loan-fees/LoanFeesView";
import { useLoanFeesPage } from "@/components/loan-fees/hooks/useLoanFeesPage";
import ModuleGate from "@/components/ui/ModuleGate";
import PageSkeleton from "@/components/ui/PageSkeleton";
import { useAuth } from "@/lib/useAuth";

export default function AdminLoanFeesPage() {
  const { loading: authLoading, logout } = useAuth({
    requireAuth: true,
    requirePasswordChanged: true,
    requireRole: "admin",
  });

  if (authLoading) return <PageSkeleton />;

  return (
    <ModuleGate module="loans">
      <LoanFeesPageContent logout={logout} />
    </ModuleGate>
  );
}

function LoanFeesPageContent({ logout }: { logout: () => void }) {
  const model = useLoanFeesPage(false, logout);

  return <LoanFeesView model={model} />;
}
