"use client";

import LoansView from "@/components/loans/LoansView";
import { useLoansPage } from "@/components/loans/hooks/useLoansPage";
import { useAuth } from "@/lib/useAuth";

export default function LoansPage() {
  const { loading: authLoading, logout } = useAuth({
    requireAuth: true,
    requirePasswordChanged: true,
    requireRole: "admin",
  });
  const model = useLoansPage(authLoading, logout);

  if (authLoading) return <main style={{ padding: 32 }}>Loading...</main>;

  return <LoansView model={model} />;
}
