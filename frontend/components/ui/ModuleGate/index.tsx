"use client";

import { useEffect, useState } from "react";
import type { ReactNode } from "react";

import { getSettings, Settings } from "@/lib/api";
import { isModuleEnabled } from "@/lib/modules";
import type { ModuleKey } from "@/lib/modules";
import ModuleDisabled from "../ModuleDisabled";
import StatusMessage from "../StatusMessage";

export default function ModuleGate({
  module,
  children,
}: {
  module: ModuleKey;
  children: ReactNode;
}) {
  const [settings, setSettings] = useState<Settings | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    getSettings()
      .then((data) => {
        if (!cancelled) setSettings(data);
      })
      .catch((e: any) => {
        if (!cancelled) setError(e.message);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (error) {
    return (
      <main style={{ padding: 32 }}>
        <StatusMessage tone="error">
          Unable to check module availability: {error}
        </StatusMessage>
      </main>
    );
  }

  if (!settings) return <main style={{ padding: 32 }}>Loading...</main>;

  if (!isModuleEnabled(settings, module)) return <ModuleDisabled module={module} />;

  return <>{children}</>;
}
