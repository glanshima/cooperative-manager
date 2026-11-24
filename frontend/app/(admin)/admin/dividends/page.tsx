"use client";

import DividendsView from "@/components/dividends/DividendsView";
import { useDividendsPage } from "@/components/dividends/hooks/useDividendsPage";
import ModuleGate from "@/components/ui/ModuleGate";
import PageSkeleton from "@/components/ui/PageSkeleton";
import { useAuth } from "@/lib/useAuth";

export default function AdminDividendsPage() {
  const { user, loading: authLoading, logout } = useAuth({
    requireAuth: true,
    requirePasswordChanged: true,
    requireRole: "admin",
  });

  if (authLoading) return <PageSkeleton />;

  return (
    <ModuleGate module="dividends">
      <DividendsPageContent permissions={user?.permissions ?? []} />
    </ModuleGate>
  );
}

function DividendsPageContent({ permissions }: { permissions: string[] }) {
  const model = useDividendsPage(permissions);

  return <DividendsView model={model} />;
}
