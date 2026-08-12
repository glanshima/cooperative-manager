"use client";

import { useEffect, useState } from "react";
import { useAuth } from "../../../lib/useAuth";
import { getSettings, updateSettings, Settings } from "../../../lib/api";

export default function AdminSettingsPage() {
  const { loading: authLoading, logout } = useAuth({
    requireAuth: true,
    requirePasswordChanged: true,
    requireRole: "admin",
  });

  const [settings, setSettings] = useState<Settings | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  async function refresh() {
    setLoading(true);
    setError(null);
    try {
      setSettings(await getSettings());
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (!authLoading) refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [authLoading]);

  async function handleSave(e: React.FormEvent) {
    e.preventDefault();
    if (!settings) return;
    setError(null);
    setSuccess(null);
    try {
      const updated = await updateSettings(settings);
      setSettings(updated);
      setSuccess("Settings saved.");
    } catch (e: any) {
      setError(e.message);
    }
  }

  if (authLoading || loading || !settings) return <main style={{ padding: 32 }}>Loading...</main>;

  return (
    <main style={{ padding: 32, maxWidth: 700, margin: "0 auto" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <h1>Settings</h1>
        <button onClick={logout}>Log out</button>
      </div>

      {error && <p style={{ color: "crimson", fontWeight: 600 }}>{error}</p>}
      {success && <p style={{ color: "green", fontWeight: 600 }}>{success}</p>}

      <form onSubmit={handleSave} style={{ display: "grid", gap: 16 }}>
        <section>
          <h2>Loan applications</h2>
          <label style={{ display: "block", marginBottom: 8 }}>
            Loan form fee
            <input
              type="number"
              step="0.01"
              value={settings.loan_form_fee}
              onChange={(e) => setSettings({ ...settings, loan_form_fee: e.target.value })}
              style={{ display: "block", padding: 8, marginTop: 4 }}
            />
          </label>
          <label style={{ display: "block" }}>
            When a restricted member applies:
            <select
              value={settings.loan_restriction_behavior}
              onChange={(e) =>
                setSettings({
                  ...settings,
                  loan_restriction_behavior: e.target.value as "block" | "warn",
                })
              }
              style={{ display: "block", padding: 8, marginTop: 4 }}
            >
              <option value="warn">Warn admin, allow application</option>
              <option value="block">Block the application entirely</option>
            </select>
          </label>
        </section>

        <section>
          <h2>Modules</h2>
          {(
            [
              ["members_module_enabled", "Members"],
              ["loans_module_enabled", "Loans"],
              ["deductions_module_enabled", "Deductions"],
              ["cashbook_module_enabled", "Cashbook"],
              ["dividends_module_enabled", "Dividends"],
            ] as const
          ).map(([key, label]) => (
            <label key={key} style={{ display: "block", marginBottom: 8 }}>
              <input
                type="checkbox"
                checked={settings[key]}
                onChange={(e) => setSettings({ ...settings, [key]: e.target.checked })}
              />{" "}
              {label} module enabled
            </label>
          ))}
        </section>

        <button type="submit">Save settings</button>
      </form>
    </main>
  );
}
