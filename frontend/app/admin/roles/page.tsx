"use client";

import RolesView from "@/components/roles/RolesView";
import { useRolesPage } from "@/components/roles/hooks/useRolesPage";
import { useAuth } from "@/lib/useAuth";

export default function AdminRolesPage() {
  const { loading: authLoading, logout } = useAuth({
    requireAuth: true,
    requirePasswordChanged: true,
    requireRole: "admin",
  });
  const model = useRolesPage(authLoading, logout);

  if (authLoading) return <main style={{ padding: 32 }}>Loading...</main>;

  return <RolesView model={model} />;
}
