"use client";

import { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
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
      <div style={{ textAlign: "center", padding: "40px 0", color: "#666" }}>
        <p>Verifying password reset link...</p>
      </div>
    );
  }

  if (success) {
    return (
      <div>
        <div
          style={{
            padding: 16,
            background: "#f0fdf4",
            border: "1px solid #bbf7d0",
            borderRadius: 6,
            color: "#166534",
            fontSize: 14,
            lineHeight: 1.5,
          }}
        >
          <strong>Password Reset Successful!</strong>
          <p style={{ margin: "8px 0 0" }}>
            Your password has been updated. You can now log in with your new credentials.
          </p>
        </div>
        <div style={{ marginTop: 24, textAlign: "center" }}>
          <button
            onClick={() => router.push("/login")}
            style={{
              padding: "10px 20px",
              fontSize: 14,
              fontWeight: 600,
              background: "#0066cc",
              color: "#fff",
              border: "none",
              borderRadius: 4,
              cursor: "pointer",
            }}
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
        <div
          style={{
            padding: 16,
            background: "#fef2f2",
            border: "1px solid #fecaca",
            borderRadius: 6,
            color: "#991b1b",
            fontSize: 14,
            lineHeight: 1.5,
          }}
        >
          <strong>Link Invalid or Expired</strong>
          <p style={{ margin: "8px 0 0" }}>{error}</p>
        </div>
        <p style={{ marginTop: 20, textAlign: "center" }}>
          <Link href="/forgot-password" style={{ color: "#0066cc", textDecoration: "none", fontWeight: 500 }}>
            Request a new password reset link →
          </Link>
        </p>
      </div>
    );
  }

  return (
    <form onSubmit={handleSubmit} style={{ display: "grid", gap: 14 }}>
      {error && (
        <div
          style={{
            padding: 12,
            background: "#fef2f2",
            border: "1px solid #fecaca",
            borderRadius: 4,
            color: "crimson",
            fontSize: 13,
            fontWeight: 500,
          }}
        >
          {error}
        </div>
      )}

      <label style={{ display: "grid", gap: 6, fontSize: 14, fontWeight: 500 }}>
        New Password
        <input
          required
          type="password"
          placeholder="Min 8 chars, 1 letter, 1 number"
          value={newPassword}
          onChange={(e) => setNewPassword(e.target.value)}
          disabled={loading}
          style={{ padding: 10, fontSize: 14, border: "1px solid #ccc", borderRadius: 4 }}
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
          style={{ padding: 10, fontSize: 14, border: "1px solid #ccc", borderRadius: 4 }}
        />
      </label>

      <p style={{ fontSize: 12, color: "#666", margin: "0" }}>
        Password policy: Minimum 8 characters with at least one letter and one number.
      </p>

      <button
        type="submit"
        disabled={loading}
        style={{
          marginTop: 8,
          padding: 10,
          fontSize: 14,
          fontWeight: 600,
          background: "#0066cc",
          color: "#fff",
          border: "none",
          borderRadius: 4,
          cursor: loading ? "not-allowed" : "pointer",
        }}
      >
        {loading ? "Updating password..." : "Set New Password"}
      </button>
    </form>
  );
}

export default function ResetPasswordPage() {
  return (
    <main
      style={{
        maxWidth: 420,
        margin: "80px auto",
        padding: 24,
        border: "1px solid #ddd",
        borderRadius: 8,
        fontFamily: "system-ui, -apple-system, sans-serif",
      }}
    >
      <h1>Reset Password</h1>
      <p style={{ color: "#666", fontSize: 14, marginBottom: 20 }}>
        Create a new password for your account.
      </p>

      <Suspense fallback={<p style={{ color: "#666" }}>Loading...</p>}>
        <ResetPasswordForm />
      </Suspense>
    </main>
  );
}
