"use client";

import LoanApplicationsView from "@/components/loan-applications/LoanApplicationsView";
import { useLoanApplicationsPage } from "@/components/loan-applications/hooks/useLoanApplicationsPage";
import { useAuth } from "@/lib/useAuth";

export default function AdminLoanApplicationsPage() {
  const { loading: authLoading, logout } = useAuth({
    requireAuth: true,
    requirePasswordChanged: true,
    requireRole: "admin",
  });
  const model = useLoanApplicationsPage(authLoading, logout);

  if (authLoading) return <main style={{ padding: 32 }}>Loading...</main>;

  return <LoanApplicationsView model={model} />;
}
