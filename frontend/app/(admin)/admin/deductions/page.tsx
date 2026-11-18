"use client";

import DeductionsView from "@/components/deductions/DeductionsView";
import { useDeductionsPage } from "@/components/deductions/hooks/useDeductionsPage";
import ModuleGate from "@/components/ui/ModuleGate";
import PageSkeleton from "@/components/ui/PageSkeleton";
import { userDisplayName } from "@/lib/names";
import { useAuth } from "@/lib/useAuth";

export default function AdminDeductionsPage() {
  const { user, loading: authLoading, logout } = useAuth({
    requireAuth: true,
    requirePasswordChanged: true,
    requireRole: "admin",
  });

  if (authLoading) return <PageSkeleton />;

  return (
    <ModuleGate module="deductions">
      <DeductionsPageContent logout={logout} identity={userDisplayName(user)} />
    </ModuleGate>
  );
}

function DeductionsPageContent({
  logout,
  identity,
}: {
  logout: () => void;
  identity: string | null;
}) {
  const model = useDeductionsPage(logout);

  return <DeductionsView model={model} identity={identity} />;
}
