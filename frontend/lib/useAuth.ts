"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { getToken, getMe, CurrentUser, logout as apiLogout } from "./api";

interface UseAuthOptions {
  /** Redirect to /login if there's no valid session at all. */
  requireAuth?: boolean;
  /** Redirect to /change-password if the user hasn't reset their temp password yet. */
  requirePasswordChanged?: boolean;
  /** Redirect to / if the logged-in user isn't this role. */
  requireRole?: "admin" | "member";
}

export function useAuth(options: UseAuthOptions = {}) {
  const router = useRouter();
  const [user, setUser] = useState<CurrentUser | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;

    async function check() {
      const token = getToken();
      if (!token) {
        if (options.requireAuth) router.replace("/login");
        setLoading(false);
        return;
      }

      try {
        const me = await getMe();
        if (cancelled) return;

        if (options.requirePasswordChanged && me.must_change_password) {
          router.replace("/change-password");
          return;
        }
        if (options.requireRole && me.role !== options.requireRole) {
          router.replace("/");
          return;
        }

        setUser(me);
      } catch {
        // token invalid/expired
        apiLogout();
        if (options.requireAuth) router.replace("/login");
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    check();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function logout() {
    apiLogout();
    router.replace("/login");
  }

  return { user, loading, logout };
}
