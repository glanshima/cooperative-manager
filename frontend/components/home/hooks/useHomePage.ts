import { useEffect, useState } from "react";

import { getSettings, Settings } from "@/lib/api";
import { isModuleEnabled } from "@/lib/modules";
import { useAuth } from "@/lib/useAuth";

export function useHomePage() {
  const { user, loading, logout } = useAuth();
  const [settings, setSettings] = useState<Settings | null>(null);
  const [settingsError, setSettingsError] = useState<string | null>(null);

  useEffect(() => {
    setSettings(null);
    setSettingsError(null);
    if (!user) return;

    let cancelled = false;
    getSettings()
      .then((data) => {
        if (!cancelled) setSettings(data);
      })
      .catch((e: any) => {
        if (!cancelled) setSettingsError(e.message);
      });
    return () => {
      cancelled = true;
    };
  }, [user]);

  return {
    auth: { user, loading, logout },
    settings,
    settingsError,
    modules: {
      membersEnabled: settings ? isModuleEnabled(settings, "members") : false,
      loansEnabled: settings ? isModuleEnabled(settings, "loans") : false,
    },
  };
}

export type HomePageModel = ReturnType<typeof useHomePage>;
