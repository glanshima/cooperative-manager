"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
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
      router.push(updated.role === "admin" ? "/members" : "/dashboard");
    } catch (e: any) {
      setError(e.message);
    } finally {
      setSubmitting(false);
    }
  }

  if (authLoading) return <main style={{ padding: 32 }}>Loading...</main>;

  return (
    <main
      style={{
        maxWidth: 400,
        margin: "80px auto",
        padding: 24,
        border: "1px solid #ddd",
        borderRadius: 8,
      }}
    >
      <h1>Change your password</h1>
      <p style={{ color: "#666" }}>
        {user?.must_change_password
          ? "You're using a temporary password. Please set a new one to continue."
          : "Set a new password."}
      </p>

      {error && <p style={{ color: "crimson", fontWeight: 600 }}>{error}</p>}

      <form onSubmit={handleSubmit} style={{ display: "grid", gap: 12 }}>
        <input
          required
          type="password"
          placeholder="Current (temporary) password"
          value={currentPassword}
          onChange={(e) => setCurrentPassword(e.target.value)}
          style={{ padding: 10 }}
        />
        <input
          required
          type="password"
          placeholder="New password (min. 8 characters)"
          value={newPassword}
          onChange={(e) => setNewPassword(e.target.value)}
          style={{ padding: 10 }}
        />
        <input
          required
          type="password"
          placeholder="Confirm new password"
          value={confirmPassword}
          onChange={(e) => setConfirmPassword(e.target.value)}
          style={{ padding: 10 }}
        />
        <button type="submit" disabled={submitting} style={{ padding: 10 }}>
          {submitting ? "Saving..." : "Change password"}
        </button>
      </form>
    </main>
  );
}
