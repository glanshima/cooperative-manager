"use client";

import DisbursementsView from "@/components/disbursements/DisbursementsView";
import { useDisbursementsPage } from "@/components/disbursements/hooks/useDisbursementsPage";
import ModuleGate from "@/components/ui/ModuleGate";
import { useAuth } from "@/lib/useAuth";

export default function AdminDisbursementsPage() {
  const { loading: authLoading, logout } = useAuth({
    requireAuth: true,
    requirePasswordChanged: true,
    requireRole: "admin",
  });

  if (authLoading) return <main style={{ padding: 32 }}>Loading...</main>;

  return (
    <ModuleGate module="loans">
      <DisbursementsPageContent logout={logout} />
    </ModuleGate>
  );
}

function DisbursementsPageContent({ logout }: { logout: () => void }) {
  const model = useDisbursementsPage(false, logout);

  return <DisbursementsView model={model} />;
}
