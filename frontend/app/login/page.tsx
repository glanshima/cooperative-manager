"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

import AuthShell from "@/components/branding/AuthShell";
import PasswordInput from "@/components/ui/PasswordInput";

import { login } from "../../lib/api";

export default function LoginPage() {
  const router = useRouter();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const result = await login(username, password);
      if (result.must_change_password) {
        router.push("/change-password");
      } else if (result.role === "admin") {
        router.push("/admin/dashboard");
      } else {
        router.push("/dashboard");
      }
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <AuthShell>
      <h1>Log in</h1>
      <p style={{ color: "var(--text-muted)" }}>
        Members: log in with your PSN. Admins: use your admin username.
      </p>

      {error && <p className="notice notice--error">{error}</p>}

      <form onSubmit={handleSubmit} style={{ display: "grid", gap: 12 }}>
        <input
          required
          autoComplete="username"
          placeholder="PSN or username"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
        />
        <PasswordInput
          required
          name="password"
          label="Password"
          placeholder="Password"
          autoComplete="current-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
        <button type="submit" className="btn btn-primary" disabled={loading}>
          {loading ? "Logging in..." : "Log in"}
        </button>
        <div style={{ textAlign: "center", marginTop: 8 }}>
          <a href="/forgot-password" style={{ fontSize: 13 }}>
            Forgot your password?
          </a>
        </div>
      </form>
    </AuthShell>
  );
}
