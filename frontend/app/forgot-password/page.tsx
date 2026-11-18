"use client";

import { useState } from "react";
import Link from "next/link";

import AuthShell from "@/components/branding/AuthShell";

import { forgotPassword } from "../../lib/api";

export default function ForgotPasswordPage() {
  const [identifier, setIdentifier] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [submitted, setSubmitted] = useState(false);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!identifier.trim()) return;

    setError(null);
    setLoading(true);
    try {
      const res = await forgotPassword(identifier.trim());
      setSuccessMessage(res.message);
      setSubmitted(true);
    } catch (e: any) {
      // Backend returns a generic message even for unknown accounts, but network/server errors
      // can be caught and displayed here.
      setError(e.message || "An error occurred while submitting your request.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <AuthShell>
      <h1>Forgot password</h1>
      <p style={{ color: "var(--text-muted)", fontSize: 14 }}>
        Enter your PSN (Members), Username, or registered Email address. If an account matches,
        we will send you a password reset link.
      </p>

      {error && <p className="notice notice--error">{error}</p>}

      {submitted ? (
        <div style={{ marginTop: 16 }}>
          <div className="notice notice--success">
            <strong>Request Received</strong>
            <p style={{ margin: 0 }}>{successMessage}</p>
          </div>
          <p style={{ marginTop: 24, textAlign: "center" }}>
            <Link href="/login" style={{ fontSize: 13 }}>
              ← Return to Login
            </Link>
          </p>
        </div>
      ) : (
        <form onSubmit={handleSubmit} style={{ display: "grid", gap: 14, marginTop: 16 }}>
          <label style={{ display: "grid", gap: 6, fontSize: 14, fontWeight: 500 }}>
            PSN, Username, or Email
            <input
              required
              type="text"
              placeholder="e.g. 12345 or admin@domain.com"
              value={identifier}
              onChange={(e) => setIdentifier(e.target.value)}
              disabled={loading}
            />
          </label>

          <button
            type="submit"
            className="btn btn-primary"
            disabled={loading || !identifier.trim()}
          >
            {loading ? "Sending instructions..." : "Send Reset Link"}
          </button>

          <div style={{ display: "flex", justifyContent: "space-between", marginTop: 8, fontSize: 13 }}>
            <Link href="/login" style={{ color: "var(--text-muted)", textDecoration: "none" }}>
              ← Back to Login
            </Link>
          </div>
        </form>
      )}
    </AuthShell>
  );
}
