"use client";

import DisbursementsView from "@/components/disbursements/DisbursementsView";
import { useDisbursementsPage } from "@/components/disbursements/hooks/useDisbursementsPage";
import AdminShell from "@/components/admin-shell/AdminShell";
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
    <AdminShell>
      <ModuleGate module="loans">
        <DisbursementsPageContent logout={logout} />
      </ModuleGate>
    </AdminShell>
  );
}

function DisbursementsPageContent({ logout }: { logout: () => void }) {
  const model = useDisbursementsPage(false, logout);

  return <DisbursementsView model={model} />;
}
