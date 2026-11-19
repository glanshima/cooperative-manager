"use client";

import { useState } from "react";

import Modal from "@/components/ui/Modal";

import styles from "./LogoutControl.module.css";

/**
 * The signed-in identity next to a log-out control, with the shared
 * confirmation step. `inline` sits in a page header; `sidebar` is the
 * one-row footer of the admin navigation.
 */
export default function LogoutControl({
  identity,
  onLogout,
  variant = "inline",
}: {
  identity?: string | null;
  onLogout: () => void;
  variant?: "inline" | "sidebar";
}) {
  const [confirming, setConfirming] = useState(false);

  const dialog = confirming && (
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
  );

  if (variant === "sidebar") {
    return (
      <div className={styles.row}>
        <span className={styles.identity} title={identity ?? undefined}>
          {identity}
        </span>
        <button
          type="button"
          className={styles.logout}
          aria-haspopup="dialog"
          aria-expanded={confirming}
          onClick={() => setConfirming(true)}
        >
          Log out
        </button>
        {dialog}
      </div>
    );
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

      {dialog}
    </div>
  );
}
