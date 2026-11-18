"use client";

import { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";

import AuthShell from "@/components/branding/AuthShell";

import { resetPassword, verifyResetToken } from "../../lib/api";

function ResetPasswordForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const token = searchParams.get("token") || "";

  const [verifying, setVerifying] = useState(true);
  const [tokenValid, setTokenValid] = useState(false);
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  useEffect(() => {
    if (!token) {
      setVerifying(false);
      setTokenValid(false);
      setError("No password reset token provided. Please request a new link.");
      return;
    }

    verifyResetToken(token)
      .then(() => {
        setTokenValid(true);
        setError(null);
      })
      .catch((err) => {
        setTokenValid(false);
        setError(err.message || "This password reset link is invalid or has expired.");
      })
      .finally(() => {
        setVerifying(false);
      });
  }, [token]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);

    if (newPassword.length < 8) {
      setError("Password must be at least 8 characters long.");
      return;
    }
    if (!/[a-zA-Z]/.test(newPassword)) {
      setError("Password must contain at least one letter.");
      return;
    }
    if (!/\d/.test(newPassword)) {
      setError("Password must contain at least one number.");
      return;
    }
    if (newPassword !== confirmPassword) {
      setError("Passwords do not match.");
      return;
    }

    setLoading(true);
    try {
      await resetPassword(token, newPassword);
      setSuccess(true);
    } catch (e: any) {
      setError(e.message || "Failed to reset password. Please try again.");
    } finally {
      setLoading(false);
    }
  }

  if (verifying) {
    return (
      <div style={{ textAlign: "center", padding: "40px 0", color: "var(--text-muted)" }}>
        <p>Verifying password reset link...</p>
      </div>
    );
  }

  if (success) {
    return (
      <div>
        <div className="notice notice--success">
          <strong>Password Reset Successful!</strong>
          <p style={{ margin: 0 }}>
            Your password has been updated. You can now log in with your new credentials.
          </p>
        </div>
        <div style={{ marginTop: 24, textAlign: "center" }}>
          <button
            onClick={() => router.push("/login")}
            className="btn btn-primary"
          >
            Go to Login
          </button>
        </div>
      </div>
    );
  }

  if (!tokenValid) {
    return (
      <div>
        <div className="notice notice--error">
          <strong>Link Invalid or Expired</strong>
          <p style={{ margin: 0 }}>{error}</p>
        </div>
        <p style={{ marginTop: 20, textAlign: "center" }}>
          <Link href="/forgot-password" style={{ fontSize: 13, fontWeight: 500 }}>
            Request a new password reset link →
          </Link>
        </p>
      </div>
    );
  }

  return (
    <form onSubmit={handleSubmit} style={{ display: "grid", gap: 14 }}>
      {error && <div className="notice notice--error">{error}</div>}

      <label style={{ display: "grid", gap: 6, fontSize: 14, fontWeight: 500 }}>
        New Password
        <input
          required
          type="password"
          placeholder="Min 8 chars, 1 letter, 1 number"
          value={newPassword}
          onChange={(e) => setNewPassword(e.target.value)}
          disabled={loading}
        />
      </label>

      <label style={{ display: "grid", gap: 6, fontSize: 14, fontWeight: 500 }}>
        Confirm New Password
        <input
          required
          type="password"
          placeholder="Re-enter new password"
          value={confirmPassword}
          onChange={(e) => setConfirmPassword(e.target.value)}
          disabled={loading}
        />
      </label>

      <p style={{ fontSize: 12, color: "var(--text-muted)", margin: "0" }}>
        Password policy: Minimum 8 characters with at least one letter and one number.
      </p>

      <button type="submit" className="btn btn-primary" disabled={loading}>
        {loading ? "Updating password..." : "Set New Password"}
      </button>
    </form>
  );
}

export default function ResetPasswordPage() {
  return (
    <AuthShell>
      <h1>Set a new password</h1>
      <p style={{ color: "var(--text-muted)", fontSize: 14, marginBottom: 20 }}>
        Create a new password for your account.
      </p>

      <Suspense fallback={<p style={{ color: "var(--text-muted)" }}>Checking your reset link...</p>}>
        <ResetPasswordForm />
      </Suspense>
    </AuthShell>
  );
}
