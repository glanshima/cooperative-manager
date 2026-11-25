import { useCallback, useEffect, useState } from "react";

import {
  getAdminDashboard,
  type AdminDashboard,
  type CurrentUser,
  type DashboardPeriodKey,
} from "@/lib/api";

export function useAdminDashboardPage(authLoading: boolean, user: CurrentUser | null) {
  const [period, setPeriod] = useState<DashboardPeriodKey>("this_month");
  const [data, setData] = useState<AdminDashboard | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [reloadToken, setReloadToken] = useState(0);

  useEffect(() => {
    if (authLoading || !user) return;

    let cancelled = false;
    setRefreshing(true);

    getAdminDashboard(period)
      .then((result) => {
        if (!cancelled) {
          setData(result);
          setError(null);
        }
      })
      .catch((e: any) => {
        // A failed period switch keeps the figures already on screen; the
        // banner says the numbers shown are the previous load's.
        if (!cancelled) setError(e.message ?? "Could not load the dashboard.");
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false);
          setRefreshing(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [authLoading, user, period, reloadToken]);

  const reload = useCallback(() => setReloadToken((token) => token + 1), []);
  const dismissError = useCallback(() => setError(null), []);

  return {
    auth: { user },
    period,
    setPeriod,
    data,
    error,
    loading,
    refreshing,
    reload,
    dismissError,
  };
}

export type AdminDashboardPageModel = ReturnType<typeof useAdminDashboardPage>;
