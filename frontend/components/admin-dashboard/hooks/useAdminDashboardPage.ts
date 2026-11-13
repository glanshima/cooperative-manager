import { useEffect, useState } from "react";

import { getSettings, Settings, CurrentUser } from "@/lib/api";
import { isModuleEnabled } from "@/lib/modules";

export function useAdminDashboardPage(
  authLoading: boolean,
  user: CurrentUser | null,
  logout: () => void
) {
  const [settings, setSettings] = useState<Settings | null>(null);
  const [settingsError, setSettingsError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (authLoading || !user) return;

    let cancelled = false;
    setLoading(true);
    setSettingsError(null);

    getSettings()
      .then((data) => {
        if (!cancelled) {
          setSettings(data);
          setLoading(false);
        }
      })
      .catch((e: any) => {
        if (!cancelled) {
          setSettingsError(e.message);
          setLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [authLoading, user]);

  return {
    auth: { user, logout },
    loading,
    settings,
    settingsError,
    modules: {
      membersEnabled: settings ? isModuleEnabled(settings, "members") : false,
      loansEnabled: settings ? isModuleEnabled(settings, "loans") : false,
      deductionsEnabled: settings ? isModuleEnabled(settings, "deductions") : false,
    },
  };
}

export type AdminDashboardPageModel = ReturnType<typeof useAdminDashboardPage>;
