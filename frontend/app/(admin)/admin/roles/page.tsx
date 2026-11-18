"use client";

import RolesView from "@/components/roles/RolesView";
import { useRolesPage } from "@/components/roles/hooks/useRolesPage";
import PageSkeleton from "@/components/ui/PageSkeleton";
import { userDisplayName } from "@/lib/names";
import { useAuth } from "@/lib/useAuth";

export default function AdminRolesPage() {
  const { user, loading: authLoading, logout } = useAuth({
    requireAuth: true,
    requirePasswordChanged: true,
    requireRole: "admin",
  });
  const model = useRolesPage(authLoading, logout);

  if (authLoading) return <PageSkeleton />;

  return <RolesView model={model} identity={userDisplayName(user)} />;
}
