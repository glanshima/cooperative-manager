"use client";

import { useEffect, useState } from "react";

import LogoutControl from "@/components/ui/LogoutControl";
import { timeOfDayGreeting } from "@/lib/greeting";

const GREETING_DELAY_MS = 5000;
const GREETING_REFRESH_MS = 60_000;

export default function DashboardHeader({
  name,
  fallbackTitle,
  identity,
  onLogout,
}: {
  name?: string | null;
  fallbackTitle: string;
  identity?: string | null;
  onLogout: () => void;
}) {
  // The session opens with a plain welcome, then settles into a greeting for
  // the time of day the officer is actually working. It keeps following the
  // clock so a page left open across noon does not stay stuck on "morning".
  const [greeting, setGreeting] = useState<string | null>(null);

  useEffect(() => {
    if (!name) return;
    let refresh: ReturnType<typeof setInterval> | undefined;
    const timer = setTimeout(() => {
      setGreeting(timeOfDayGreeting(new Date()));
      refresh = setInterval(() => setGreeting(timeOfDayGreeting(new Date())), GREETING_REFRESH_MS);
    }, GREETING_DELAY_MS);
    return () => {
      clearTimeout(timer);
      if (refresh) clearInterval(refresh);
    };
  }, [name]);

  const title = name ? (greeting ? `${greeting}, ${name}` : `Welcome, ${name}`) : fallbackTitle;

  return (
    <div
      style={{
        display: "flex",
        justifyContent: "space-between",
        alignItems: "flex-start",
        marginBottom: 16,
      }}
    >
      <h1 style={{ margin: 0, fontSize: 16, fontWeight: 600 }}>{title}</h1>
      <LogoutControl identity={identity} onLogout={onLogout} />
    </div>
  );
}
