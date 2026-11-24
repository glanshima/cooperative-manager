"use client";

import CashbookView from "@/components/cashbook/CashbookView";
import { useCashbookPage } from "@/components/cashbook/hooks/useCashbookPage";
import ModuleGate from "@/components/ui/ModuleGate";
import PageSkeleton from "@/components/ui/PageSkeleton";
import { useAuth } from "@/lib/useAuth";

export default function AdminCashbookPage() {
  const { user, loading: authLoading, logout } = useAuth({
    requireAuth: true,
    requirePasswordChanged: true,
    requireRole: "admin",
  });

  if (authLoading) return <PageSkeleton />;

  return (
    <ModuleGate module="cashbook">
      <CashbookPageContent permissions={user?.permissions ?? []} />
    </ModuleGate>
  );
}

function CashbookPageContent({ permissions }: { permissions: string[] }) {
  const model = useCashbookPage(permissions);

  return <CashbookView model={model} />;
}
