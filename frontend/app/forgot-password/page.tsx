"use client";

import { useState } from "react";
import Link from "next/link";
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
      <h1>Password Recovery</h1>
      <p style={{ color: "#666", fontSize: 14 }}>
        Enter your PSN (Members), Username, or registered Email address. If an account matches,
        we will send you a password reset link.
      </p>

      {error && <p style={{ color: "crimson", fontWeight: 600 }}>{error}</p>}

      {submitted ? (
        <div style={{ marginTop: 16 }}>
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
            <strong>Request Received</strong>
            <p style={{ margin: "8px 0 0" }}>{successMessage}</p>
          </div>
          <p style={{ marginTop: 24, textAlign: "center" }}>
            <Link href="/login" style={{ color: "#0066cc", textDecoration: "none" }}>
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
              style={{ padding: 10, fontSize: 14, border: "1px solid #ccc", borderRadius: 4 }}
            />
          </label>

          <button
            type="submit"
            disabled={loading || !identifier.trim()}
            style={{
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
            {loading ? "Sending instructions..." : "Send Reset Link"}
          </button>

          <div style={{ display: "flex", justifyContent: "space-between", marginTop: 8, fontSize: 13 }}>
            <Link href="/login" style={{ color: "#666", textDecoration: "none" }}>
              ← Back to Login
            </Link>
          </div>
        </form>
      )}
    </main>
  );
}
