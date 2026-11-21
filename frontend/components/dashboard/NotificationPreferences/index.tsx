"use client";

import { useEffect, useRef, useState } from "react";

import {
  getNotificationPreferences,
  updateNotificationPreferences,
  NotificationPreferences,
} from "@/lib/api";

const cardStyle = {
  border: "1px solid #ddd",
  borderRadius: 8,
  padding: 16,
  marginTop: 24,
} as const;

const toggleStyle = {
  display: "flex",
  alignItems: "flex-start",
  gap: 8,
  padding: "6px 0",
  fontSize: 14,
} as const;

export default function NotificationPreferencesCard() {
  const [preferences, setPreferences] = useState<NotificationPreferences | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const savedTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    let active = true;
    getNotificationPreferences()
      .then((value) => {
        if (active) setPreferences(value);
      })
      .catch((e: any) => {
        if (active) setError(e.message);
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, []);

  useEffect(
    () => () => {
      if (savedTimer.current) clearTimeout(savedTimer.current);
    },
    []
  );

  function toggle(key: keyof NotificationPreferences) {
    setPreferences((current) => (current ? { ...current, [key]: !current[key] } : current));
    setSaved(false);
  }

  async function save() {
    if (!preferences) return;
    setSaving(true);
    setError(null);
    setSaved(false);
    try {
      const updated = await updateNotificationPreferences(preferences);
      setPreferences(updated);
      setSaved(true);
      if (savedTimer.current) clearTimeout(savedTimer.current);
      savedTimer.current = setTimeout(() => setSaved(false), 4000);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <section style={cardStyle}>
      <h2 style={{ marginTop: 0 }}>Email notifications</h2>
      <p style={{ color: "#666", fontSize: 14, marginTop: 0 }}>
        Choose which automatic emails you receive. Your in-app notifications always show
        everything, and account and security emails cannot be switched off.
      </p>

      {loading && <p style={{ fontSize: 14, color: "#666" }}>Loading…</p>}

      {!loading && preferences && (
        <>
          <label style={toggleStyle}>
            <input
              type="checkbox"
              checked={preferences.email_loan}
              onChange={() => toggle("email_loan")}
              disabled={saving}
            />
            <span>Loan applications, decisions and disbursements</span>
          </label>
          <label style={toggleStyle}>
            <input
              type="checkbox"
              checked={preferences.email_repayment}
              onChange={() => toggle("email_repayment")}
              disabled={saving}
            />
            <span>Repayment confirmations</span>
          </label>
          <div className="toolbar" style={{ marginTop: 8 }}>
            <button type="button" onClick={save} disabled={saving}>
              {saving ? "Saving…" : "Save preferences"}
            </button>
          </div>
        </>
      )}

      {error && <p style={{ color: "crimson", fontSize: 14, marginBottom: 0 }}>{error}</p>}
      {saved && <p style={{ color: "green", fontSize: 14, marginBottom: 0 }}>Preferences saved.</p>}
    </section>
  );
}
