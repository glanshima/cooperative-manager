"use client";

import LoansView from "@/components/loans/LoansView";
import { useLoansPage } from "@/components/loans/hooks/useLoansPage";
import AdminShell from "@/components/admin-shell/AdminShell";
import ModuleGate from "@/components/ui/ModuleGate";
import { useAuth } from "@/lib/useAuth";

export default function LoansPage() {
  const { loading: authLoading, logout } = useAuth({
    requireAuth: true,
    requirePasswordChanged: true,
    requireRole: "admin",
  });

  if (authLoading) return <main style={{ padding: 32 }}>Loading...</main>;

  return (
    <AdminShell>
      <ModuleGate module="loans">
        <LoansPageContent logout={logout} />
      </ModuleGate>
    </AdminShell>
  );
}

function LoansPageContent({ logout }: { logout: () => void }) {
  const model = useLoansPage(false, logout);

  return <LoansView model={model} />;
}
