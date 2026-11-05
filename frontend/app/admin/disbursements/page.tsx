"use client";

import DisbursementsView from "@/components/disbursements/DisbursementsView";
import { useDisbursementsPage } from "@/components/disbursements/hooks/useDisbursementsPage";
import { useAuth } from "@/lib/useAuth";

export default function AdminDisbursementsPage() {
  const { loading: authLoading, logout } = useAuth({
    requireAuth: true,
    requirePasswordChanged: true,
    requireRole: "admin",
  });
  const model = useDisbursementsPage(authLoading, logout);

  if (authLoading) return <main style={{ padding: 32 }}>Loading...</main>;

  return <DisbursementsView model={model} />;
}
