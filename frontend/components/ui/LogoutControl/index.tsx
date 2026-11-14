"use client";

import { useEffect, useRef, useState } from "react";
import type { KeyboardEvent, MouseEvent } from "react";

const DIALOG_TITLE_ID = "logout-confirm-title";

/**
 * The signed-in identity above a log-out button, with the shared confirmation
 * step. Every screen renders this so the name sits above log out everywhere.
 */
export default function LogoutControl({
  identity,
  onLogout,
}: {
  identity?: string | null;
  onLogout: () => void;
}) {
  const [confirming, setConfirming] = useState(false);
  const cancelRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (confirming) cancelRef.current?.focus();
  }, [confirming]);

  function closeConfirmation() {
    setConfirming(false);
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
    <div style={{ textAlign: "right" }}>
      {identity ? (
        <p style={{ margin: 0, fontSize: 13, color: "#555" }}>{identity}</p>
      ) : null}
      <button
        type="button"
        aria-haspopup="dialog"
        aria-expanded={confirming}
        onClick={() => setConfirming(true)}
      >
        Log out
      </button>

      {confirming && (
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
              textAlign: "left",
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
