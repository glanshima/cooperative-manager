"use client";

import AdminUsersView from "@/components/admin-users/AdminUsersView";
import { useAdminUsersPage } from "@/components/admin-users/hooks/useAdminUsersPage";
import PageSkeleton from "@/components/ui/PageSkeleton";
import { userDisplayName } from "@/lib/names";
import { useAuth } from "@/lib/useAuth";

export default function AdminUsersPage() {
  const { user, loading, logout } = useAuth({
    requireAuth: true,
    requirePasswordChanged: true,
    requireRole: "admin",
  });
  const model = useAdminUsersPage(loading, logout);

  if (loading || model.loading) return <PageSkeleton />;

  return <AdminUsersView model={model} identity={userDisplayName(user)} />;
}
