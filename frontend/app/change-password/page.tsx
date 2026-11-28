"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

import AuthShell from "@/components/branding/AuthShell";
import PageSkeleton from "@/components/ui/PageSkeleton";
import PasswordInput from "@/components/ui/PasswordInput";

import { useAuth } from "../../lib/useAuth";
import { changePassword } from "../../lib/api";

export default function ChangePasswordPage() {
  const router = useRouter();
  const { user, loading: authLoading } = useAuth({ requireAuth: true });

  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);

    if (newPassword.length < 8) {
      setError("New password must be at least 8 characters.");
      return;
    }
    if (newPassword !== confirmPassword) {
      setError("Passwords don't match.");
      return;
    }

    setSubmitting(true);
    try {
      const updated = await changePassword(currentPassword, newPassword);
      router.push(updated.role === "admin" ? "/admin/dashboard" : "/dashboard");
    } catch (e: any) {
      setError(e.message);
    } finally {
      setSubmitting(false);
    }
  }

  if (authLoading) return <PageSkeleton />;

  return (
    <AuthShell>
      <h1>Change your password</h1>
      <p style={{ color: "var(--text-muted)" }}>
        {user?.must_change_password
          ? "You're using a temporary password. Please set a new one to continue."
          : "Set a new password."}
      </p>

      {error && <p className="notice notice--error">{error}</p>}

      <form onSubmit={handleSubmit} style={{ display: "grid", gap: 12 }}>
        <PasswordInput
          required
          name="currentPassword"
          label="Current (temporary) password"
          autoComplete="current-password"
          value={currentPassword}
          onChange={(e) => setCurrentPassword(e.target.value)}
        />
        <PasswordInput
          required
          name="newPassword"
          label="New password (min. 8 characters)"
          autoComplete="new-password"
          value={newPassword}
          onChange={(e) => setNewPassword(e.target.value)}
        />
        <PasswordInput
          required
          name="confirmPassword"
          label="Confirm new password"
          autoComplete="new-password"
          value={confirmPassword}
          onChange={(e) => setConfirmPassword(e.target.value)}
        />
        <button type="submit" className="btn btn-primary" disabled={submitting}>
          {submitting ? "Saving..." : "Change password"}
        </button>
      </form>
    </AuthShell>
  );
}
