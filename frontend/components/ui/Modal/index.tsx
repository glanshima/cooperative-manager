"use client";

import { useEffect, useId, useRef, useState } from "react";
import type { KeyboardEvent, ReactNode } from "react";
import { createPortal } from "react-dom";

import CloseButton from "@/components/ui/CloseButton";

import styles from "./Modal.module.css";

export default function Modal({
  title,
  onClose,
  busy = false,
  closeLabel = "Close",
  hint,
  testId,
  maxWidth,
  children,
}: {
  title: string;
  onClose: () => void;
  /** While busy, Escape, the backdrop and the close button are locked. */
  busy?: boolean;
  closeLabel?: string;
  hint?: string;
  testId?: string;
  maxWidth?: number;
  children: ReactNode;
}) {
  const titleId = useId();
  const dialogRef = useRef<HTMLDivElement>(null);
  const [mounted, setMounted] = useState(false);

  // Rendered into <body>: a dialog opened from inside the sidebar would
  // otherwise be sized against the drawer, because its transform makes the
  // drawer the containing block for position: fixed.
  useEffect(() => setMounted(true), []);

  // Moving focus into the dialog on open and back to whatever opened it on
  // close is what makes this a dialog rather than an inline form that
  // happens to sit on top of the page.
  useEffect(() => {
    if (!mounted) return;
    const opener = document.activeElement as HTMLElement | null;
    const preferred =
      dialogRef.current?.querySelector<HTMLElement>("[data-initial-focus]:not([disabled])") ??
      dialogRef.current?.querySelector<HTMLElement>(
        "input:not([disabled]), select:not([disabled]), textarea:not([disabled])"
      );
    (preferred ?? dialogRef.current)?.focus();
    return () => opener?.focus?.();
  }, [mounted]);

  function handleKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    if (event.key === "Escape") {
      if (busy) return;
      event.stopPropagation();
      onClose();
      return;
    }
    if (event.key !== "Tab") return;
    const focusable = dialogRef.current?.querySelectorAll<HTMLElement>(
      'button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), a[href], [tabindex]:not([tabindex="-1"])'
    );
    if (!focusable || focusable.length === 0) return;
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  }

  if (!mounted) return null;

  return createPortal(
    <div
      className={styles.backdrop}
      data-testid={testId}
      onClick={(event) => {
        // A click on the backdrop itself closes; anything inside the dialog
        // does not, however far the content scrolls.
        if (event.target === event.currentTarget && !busy) onClose();
      }}
    >
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex={-1}
        className={styles.dialog}
        style={maxWidth ? { maxWidth } : undefined}
        onKeyDown={handleKeyDown}
      >
        <div className={styles.header}>
          <h2 id={titleId} className={styles.title}>
            {title}
          </h2>
          <CloseButton label={closeLabel} disabled={busy} onClick={onClose} />
        </div>
        {hint && <p className={styles.hint}>{hint}</p>}
        {children}
      </div>
    </div>,
    document.body
  );
}
