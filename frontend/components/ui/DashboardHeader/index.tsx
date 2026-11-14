"use client";

import { useEffect, useRef, useState } from "react";
import type { KeyboardEvent, MouseEvent } from "react";

import { timeOfDayGreeting } from "@/lib/greeting";

const GREETING_DELAY_MS = 5000;
const DIALOG_TITLE_ID = "logout-confirm-title";

export default function DashboardHeader({
  name,
  fallbackTitle,
  username,
  onLogout,
}: {
  name?: string | null;
  fallbackTitle: string;
  username?: string | null;
  onLogout: () => void;
}) {
  // The session opens with a plain welcome, then settles into a greeting for
  // the time of day the officer is actually working.
  const [greeting, setGreeting] = useState<string | null>(null);
  const [confirmingLogout, setConfirmingLogout] = useState(false);
  const cancelRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!name) return;
    const timer = setTimeout(() => setGreeting(timeOfDayGreeting(new Date())), GREETING_DELAY_MS);
    return () => clearTimeout(timer);
  }, [name]);

  useEffect(() => {
    if (confirmingLogout) cancelRef.current?.focus();
  }, [confirmingLogout]);

  const title = name ? (greeting ? `${greeting}, ${name}` : `Welcome, ${name}`) : fallbackTitle;

  function closeConfirmation() {
    setConfirmingLogout(false);
  }

  function handleDialogKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    if (event.key === "Escape") {
      event.stopPropagation();
      closeConfirmation();
    }
  }

  function handleBackdropClick(event: MouseEvent<HTMLDivElement>) {
    if (event.target === event.currentTarget) closeConfirmation();
  }

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
      <div style={{ textAlign: "right" }}>
        {username ? (
          <p style={{ margin: 0, fontSize: 13, color: "#555" }}>{username}</p>
        ) : null}
        <button
          type="button"
          aria-haspopup="dialog"
          aria-expanded={confirmingLogout}
          onClick={() => setConfirmingLogout(true)}
        >
          Log out
        </button>
      </div>

      {confirmingLogout && (
        <div
          onClick={handleBackdropClick}
          style={{
            position: "fixed",
            inset: 0,
            background: "rgba(0,0,0,0.5)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            zIndex: 1000,
          }}
        >
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby={DIALOG_TITLE_ID}
            onKeyDown={handleDialogKeyDown}
            style={{
              background: "white",
              borderRadius: 8,
              padding: 24,
              maxWidth: 380,
              width: "90%",
            }}
          >
            <h2 id={DIALOG_TITLE_ID} style={{ marginTop: 0 }}>
              Log out?
            </h2>
            <p style={{ color: "#555" }}>
              You will be signed out and will need to sign in again to continue.
            </p>
            <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
              <button ref={cancelRef} type="button" onClick={closeConfirmation}>
                Cancel
              </button>
              <button type="button" onClick={onLogout}>
                Log out
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
