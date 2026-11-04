"use client";

import MembersView from "@/components/members/MembersView";
import { useMembersPage } from "@/components/members/hooks/useMembersPage";
import { useAuth } from "@/lib/useAuth";

export default function MembersPage() {
  const { loading, logout } = useAuth({
    requireAuth: true,
    requirePasswordChanged: true,
    requireRole: "admin",
  });
  const model = useMembersPage(loading, logout);

  if (loading) return <main style={{ padding: 32 }}>Loading...</main>;

  return <MembersView model={model} />;
}
