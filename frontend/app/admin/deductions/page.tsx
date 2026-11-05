"use client";

import DeductionsView from "@/components/deductions/DeductionsView";
import { useDeductionsPage } from "@/components/deductions/hooks/useDeductionsPage";
import ModuleGate from "@/components/ui/ModuleGate";
import { useAuth } from "@/lib/useAuth";

export default function AdminDeductionsPage() {
  const { loading: authLoading, logout } = useAuth({
    requireAuth: true,
    requirePasswordChanged: true,
    requireRole: "admin",
  });

  if (authLoading) return <main style={{ padding: 32 }}>Loading...</main>;

  return (
    <ModuleGate module="deductions">
      <DeductionsPageContent logout={logout} />
    </ModuleGate>
  );
}

function DeductionsPageContent({ logout }: { logout: () => void }) {
  const model = useDeductionsPage(logout);

  return <DeductionsView model={model} />;
}
