import { useEffect, useState } from "react";
import type { FormEvent } from "react";

import { useBranding } from "@/components/branding/BrandingProvider";
import { getSettings, updateSettings, Settings } from "@/lib/api";

export function useSettingsPage(authLoading: boolean, logout: () => void) {
  const { setBranding } = useBranding();
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

  function setField<K extends keyof Settings>(key: K, value: Settings[K]) {
    setSettings((current) => (current ? { ...current, [key]: value } : current));
  }

  async function handleSave(e: FormEvent) {
    e.preventDefault();
    if (!settings) return;
    setError(null);
    setSuccess(null);
    try {
      const saved = await updateSettings(settings);
      setSettings(saved);
      setBranding({
        cooperative_name: saved.cooperative_name,
        cooperative_short_name: saved.cooperative_short_name,
        cooperative_monogram: saved.cooperative_monogram,
        logo_url: saved.logo_url,
      });
      setSuccess("Settings saved.");
    } catch (e: any) {
      setError(e.message);
    }
  }

  return {
    auth: { logout },
    feedback: { error, success },
    loading,
    settings,
    setField,
    save: handleSave,
  };
}

export type SettingsPageModel = ReturnType<typeof useSettingsPage>;
