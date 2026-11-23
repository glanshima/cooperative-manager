"use client";

import MembersView from "@/components/members/MembersView";
import { useMembersPage } from "@/components/members/hooks/useMembersPage";
import ModuleGate from "@/components/ui/ModuleGate";
import PageSkeleton from "@/components/ui/PageSkeleton";
import { useAuth } from "@/lib/useAuth";

export default function MembersPage() {
  const { loading, user, logout } = useAuth({
    requireAuth: true,
    requirePasswordChanged: true,
    requireRole: "admin",
  });

  if (loading) return <PageSkeleton />;

  return (
    <ModuleGate module="members">
      <MembersPageContent logout={logout} permissions={user?.permissions ?? []} />
    </ModuleGate>
  );
}

function MembersPageContent({
  logout,
  permissions,
}: {
  logout: () => void;
  permissions: string[];
}) {
  const model = useMembersPage(false, logout, permissions);

  return <MembersView model={model} />;
}
