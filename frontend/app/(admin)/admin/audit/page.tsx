"use client";

import AuditView from "@/components/audit/AuditView";
import { useAuditPage } from "@/components/audit/hooks/useAuditPage";
import PageSkeleton from "@/components/ui/PageSkeleton";
import { userDisplayName } from "@/lib/names";
import { useAuth } from "@/lib/useAuth";

export default function AdminAuditPage() {
  const { user, loading: authLoading, logout } = useAuth({
    requireAuth: true,
    requirePasswordChanged: true,
    requireRole: "admin",
  });
  const model = useAuditPage(authLoading, logout);

  if (authLoading) return <PageSkeleton />;

  return <AuditView model={model} identity={userDisplayName(user)} />;
}
