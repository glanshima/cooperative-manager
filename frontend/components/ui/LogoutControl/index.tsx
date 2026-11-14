"use client";

import { useState } from "react";

import Modal from "@/components/ui/Modal";

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
        <Modal
          title="Log out?"
          onClose={() => setConfirming(false)}
          closeLabel="Close log out dialog"
          maxWidth={380}
        >
          <p style={{ color: "#555" }}>
            You will be signed out and will need to sign in again to continue.
          </p>
          <div className="toolbar toolbar--end">
            <button type="button" onClick={() => setConfirming(false)}>
              Cancel
            </button>
            <button type="button" onClick={onLogout}>
              Log out
            </button>
          </div>
        </Modal>
      )}
    </div>
  );
}
