"use client";

import { createContext, useContext, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";

import { getBranding } from "@/lib/api";
import type { Branding } from "@/lib/api";
import {
  COOPERATIVE_MONOGRAM,
  COOPERATIVE_NAME,
  COOPERATIVE_SHORT_NAME,
} from "@/lib/branding";

// Deployment defaults, used until the branding fetch settles and whenever it
// cannot be reached -- a signed-out screen must still wear the cooperative's
// identity rather than an empty header.
export const DEFAULT_BRANDING: Branding = {
  cooperative_name: COOPERATIVE_NAME,
  cooperative_short_name: COOPERATIVE_SHORT_NAME,
  cooperative_monogram: COOPERATIVE_MONOGRAM,
  logo_url: null,
};

interface BrandingContextValue {
  branding: Branding;
  setBranding: (patch: Partial<Branding>) => void;
}

const BrandingContext = createContext<BrandingContextValue | null>(null);

export function useBranding(): BrandingContextValue {
  return (
    useContext(BrandingContext) ?? {
      branding: DEFAULT_BRANDING,
      // Components rendered on their own (tests, isolated previews) have no
      // provider to update; discarding the patch is the correct no-op.
      setBranding: () => {},
    }
  );
}

export default function BrandingProvider({ children }: { children: ReactNode }) {
  const [branding, setBrandingState] = useState<Branding>(DEFAULT_BRANDING);

  useEffect(() => {
    let cancelled = false;
    getBranding()
      .then((data) => {
        if (!cancelled) setBrandingState(data);
      })
      .catch(() => {
        // Keep the deployment defaults; a branding fetch failure must never
        // block sign-in or the dashboard.
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const value = useMemo<BrandingContextValue>(
    () => ({
      branding,
      setBranding: (patch) => setBrandingState((current) => ({ ...current, ...patch })),
    }),
    [branding]
  );

  return <BrandingContext.Provider value={value}>{children}</BrandingContext.Provider>;
}
