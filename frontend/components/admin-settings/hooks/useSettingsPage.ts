import { useEffect, useState } from "react";
import type { FormEvent } from "react";

import { useBranding } from "@/components/branding/BrandingProvider";
import { getSettings, updateSettings, Settings } from "@/lib/api";

export type SettingsSaveScope = "branding" | "configuration";

// The server splits the same PUT by field: branding fields need
// branding.manage, everything else needs admin.settings_manage. Sending
// only the fields of the saved scope keeps a partial-permission account
// from tripping the other side's check.
const SCOPE_FIELDS: Record<SettingsSaveScope, Array<keyof Settings>> = {
  branding: ["cooperative_name", "cooperative_short_name", "cooperative_monogram"],
  configuration: [
    "loan_restriction_behavior",
    "loan_interest_mode",
    "loan_interest_spread_months",
    "loan_form_fee",
    "members_module_enabled",
    "loans_module_enabled",
    "deductions_module_enabled",
    "cashbook_module_enabled",
    "dividends_module_enabled",
  ],
};

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

  async function handleSave(e: FormEvent, scope: SettingsSaveScope) {
    e.preventDefault();
    if (!settings) return;
    setError(null);
    setSuccess(null);
    try {
      const payload = Object.fromEntries(
        SCOPE_FIELDS[scope].map((field) => [field, settings[field]])
      ) as Partial<Settings>;
      const saved = await updateSettings(payload);
      setSettings(saved);
      if (scope === "branding") {
        setBranding({
          cooperative_name: saved.cooperative_name,
          cooperative_short_name: saved.cooperative_short_name,
          cooperative_monogram: saved.cooperative_monogram,
          logo_url: saved.logo_url,
        });
      }
      setSuccess(scope === "branding" ? "Branding saved." : "Settings saved.");
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
    saveBranding: (e: FormEvent) => handleSave(e, "branding"),
    saveConfiguration: (e: FormEvent) => handleSave(e, "configuration"),
  };
}

export type SettingsPageModel = ReturnType<typeof useSettingsPage>;
