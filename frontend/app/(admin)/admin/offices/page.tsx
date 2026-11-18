"use client";

import OfficesView from "@/components/offices/OfficesView";
import { useOfficesPage } from "@/components/offices/hooks/useOfficesPage";
import PageSkeleton from "@/components/ui/PageSkeleton";
import { userDisplayName } from "@/lib/names";
import { useAuth } from "@/lib/useAuth";

export default function AdminOfficesPage() {
  const { user, loading: authLoading, logout } = useAuth({
    requireAuth: true,
    requirePasswordChanged: true,
    requireRole: "admin",
  });
  const model = useOfficesPage(authLoading, logout);

  if (authLoading) return <PageSkeleton />;

  return <OfficesView model={model} identity={userDisplayName(user)} />;
}
