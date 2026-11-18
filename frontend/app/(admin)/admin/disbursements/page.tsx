"use client";

import DisbursementsView from "@/components/disbursements/DisbursementsView";
import { useDisbursementsPage } from "@/components/disbursements/hooks/useDisbursementsPage";
import ModuleGate from "@/components/ui/ModuleGate";
import PageSkeleton from "@/components/ui/PageSkeleton";
import { userDisplayName } from "@/lib/names";
import { useAuth } from "@/lib/useAuth";

export default function AdminDisbursementsPage() {
  const { user, loading: authLoading, logout } = useAuth({
    requireAuth: true,
    requirePasswordChanged: true,
    requireRole: "admin",
  });

  if (authLoading) return <PageSkeleton />;

  return (
    <ModuleGate module="loans">
      <DisbursementsPageContent logout={logout} identity={userDisplayName(user)} />
    </ModuleGate>
  );
}

function DisbursementsPageContent({
  logout,
  identity,
}: {
  logout: () => void;
  identity: string | null;
}) {
  const model = useDisbursementsPage(false, logout);

  return <DisbursementsView model={model} identity={identity} />;
}
