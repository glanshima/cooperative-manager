"use client";

import LoanRepaymentsView from "@/components/loan-repayments/LoanRepaymentsView";
import { useLoanRepaymentsPage } from "@/components/loan-repayments/hooks/useLoanRepaymentsPage";
import ModuleGate from "@/components/ui/ModuleGate";
import PageSkeleton from "@/components/ui/PageSkeleton";
import { hasPermission } from "@/lib/permissions";
import { useAuth } from "@/lib/useAuth";

export default function AdminLoanRepaymentsPage() {
  const { loading: authLoading, logout, user } = useAuth({
    requireAuth: true,
    requirePasswordChanged: true,
    requireRole: "admin",
  });

  if (authLoading || !user) return <PageSkeleton />;

  return (
    <ModuleGate module="loans">
      <LoanRepaymentsPageContent
        logout={logout}
        canViewHistory={hasPermission(user.permissions ?? [], "repayment.view")}
      />
    </ModuleGate>
  );
}

function LoanRepaymentsPageContent({
  logout,
  canViewHistory,
}: {
  logout: () => void;
  canViewHistory: boolean;
}) {
  const model = useLoanRepaymentsPage(false, logout, canViewHistory);

  return <LoanRepaymentsView model={model} />;
}
