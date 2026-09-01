"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
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
        router.push("/members");
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
    <main
      style={{
        maxWidth: 400,
        margin: "80px auto",
        padding: 24,
        border: "1px solid #ddd",
        borderRadius: 8,
      }}
    >
      <h1>MACT Cooperative Manager</h1>
      <p style={{ color: "#666" }}>
        Members: log in with your PSN. Admins: use your admin username.
      </p>

      {error && <p style={{ color: "crimson", fontWeight: 600 }}>{error}</p>}

      <form onSubmit={handleSubmit} style={{ display: "grid", gap: 12 }}>
        <input
          required
          placeholder="PSN or username"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          style={{ padding: 10 }}
        />
        <input
          required
          type="password"
          placeholder="Password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          style={{ padding: 10 }}
        />
        <button type="submit" disabled={loading} style={{ padding: 10, cursor: loading ? "not-allowed" : "pointer" }}>
          {loading ? "Logging in..." : "Log in"}
        </button>
        <div style={{ textAlign: "center", marginTop: 8 }}>
          <a href="/forgot-password" style={{ color: "#0066cc", fontSize: 13, textDecoration: "none" }}>
            Forgot your password?
          </a>
        </div>
      </form>
    </main>
  );
}
