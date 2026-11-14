"use client";

import MembersView from "@/components/members/MembersView";
import { useMembersPage } from "@/components/members/hooks/useMembersPage";
import AdminShell from "@/components/admin-shell/AdminShell";
import ModuleGate from "@/components/ui/ModuleGate";
import { userDisplayName } from "@/lib/names";
import { useAuth } from "@/lib/useAuth";

export default function MembersPage() {
  const { user, loading, logout } = useAuth({
    requireAuth: true,
    requirePasswordChanged: true,
    requireRole: "admin",
  });

  if (loading) return <main style={{ padding: 32 }}>Loading...</main>;

  return (
    <AdminShell>
      <ModuleGate module="members">
        <MembersPageContent logout={logout} identity={userDisplayName(user)} />
      </ModuleGate>
    </AdminShell>
  );
}

function MembersPageContent({
  logout,
  identity,
}: {
  logout: () => void;
  identity: string | null;
}) {
  const model = useMembersPage(false, logout);

  return <MembersView model={model} identity={identity} />;
}
