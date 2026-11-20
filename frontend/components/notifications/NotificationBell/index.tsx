"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

import type { Notification } from "@/lib/api";

import { useNotifications } from "../hooks/useNotifications";
import styles from "./NotificationBell.module.css";

const PANEL_WIDTH = 340;
const VIEWPORT_GAP = 8;

function formatWhen(value: string): string {
  // Timestamps are naive UTC; without the suffix a browser would read
  // them as local time and show the wrong hour.
  const iso = /[zZ]|[+-]\d{2}:?\d{2}$/.test(value) ? value : `${value}Z`;
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? "" : date.toLocaleString();
}

export default function NotificationBell({ tone = "light" }: { tone?: "light" | "inverse" }) {
  const router = useRouter();
  const { items, unreadCount, total, loading, error, refresh, markRead, markAllRead } =
    useNotifications();
  const [open, setOpen] = useState(false);
  const [mounted, setMounted] = useState(false);
  const [position, setPosition] = useState<{ top: number; left: number; maxHeight: number } | null>(
    null
  );
  const buttonRef = useRef<HTMLButtonElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);

  useEffect(() => setMounted(true), []);

  const close = useCallback((returnFocus = false) => {
    setOpen(false);
    if (returnFocus) buttonRef.current?.focus();
  }, []);

  // The sidebar scrolls and clips its own overflow (and is transformed on
  // phones), so the panel is portalled to the body and anchored to the
  // button's live position instead of being nested beside it.
  useEffect(() => {
    if (!open) return;
    const update = () => {
      const rect = buttonRef.current?.getBoundingClientRect();
      if (!rect) return;
      const width = Math.min(PANEL_WIDTH, window.innerWidth - VIEWPORT_GAP * 2);
      const left = Math.max(
        VIEWPORT_GAP,
        Math.min(rect.right - width, window.innerWidth - width - VIEWPORT_GAP)
      );
      const top = rect.bottom + VIEWPORT_GAP;
      setPosition({
        top,
        left,
        maxHeight: Math.max(160, window.innerHeight - top - VIEWPORT_GAP),
      });
    };
    update();
    window.addEventListener("resize", update);
    window.addEventListener("scroll", update, true);
    return () => {
      window.removeEventListener("resize", update);
      window.removeEventListener("scroll", update, true);
    };
  }, [open]);

  useEffect(() => {
    if (!open) return;
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") close(true);
    }
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [open, close]);

  useEffect(() => {
    if (!open) return;
    function handlePointerDown(event: PointerEvent) {
      const target = event.target as Node;
      if (buttonRef.current?.contains(target) || panelRef.current?.contains(target)) return;
      setOpen(false);
    }
    document.addEventListener("pointerdown", handlePointerDown);
    return () => document.removeEventListener("pointerdown", handlePointerDown);
  }, [open]);

  function toggle() {
    if (!open) refresh();
    setOpen((current) => !current);
  }

  async function openItem(item: Notification) {
    if (!item.is_read) markRead(item.id);
    close();
    if (item.link_path) router.push(item.link_path);
  }

  const badge = unreadCount > 99 ? "99+" : String(unreadCount);

  return (
    <div className={styles.wrapper}>
      <button
        ref={buttonRef}
        type="button"
        className={styles.button}
        data-tone={tone}
        aria-label={unreadCount > 0 ? `Notifications, ${unreadCount} unread` : "Notifications"}
        aria-haspopup="dialog"
        aria-expanded={open}
        onClick={toggle}
      >
        <svg
          aria-hidden="true"
          viewBox="0 0 24 24"
          width="18"
          height="18"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.8"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <path d="M18 8a6 6 0 0 0-12 0c0 7-3 9-3 9h18s-3-2-3-9" />
          <path d="M13.7 21a2 2 0 0 1-3.4 0" />
        </svg>
        {unreadCount > 0 && (
          <span className={styles.badge} aria-hidden="true">
            {badge}
          </span>
        )}
      </button>

      {open && mounted && position
        ? createPortal(
            <div
              ref={panelRef}
              className={styles.panel}
              role="dialog"
              aria-label="Notifications"
              style={{
                top: position.top,
                left: position.left,
                maxHeight: position.maxHeight,
              }}
            >
              <div className={styles.panelHeader}>
                <strong>Notifications</strong>
                {unreadCount > 0 && (
                  <button type="button" className={styles.markAll} onClick={markAllRead}>
                    Mark all as read
                  </button>
                )}
              </div>

              {error && <p className={styles.empty}>{error}</p>}
              {!error && loading && items.length === 0 && <p className={styles.empty}>Loading…</p>}
              {!error && !loading && items.length === 0 && (
                <p className={styles.empty}>No notifications yet.</p>
              )}

              {items.length > 0 && (
                <ul className={styles.list}>
                  {items.map((item) => (
                    <li key={item.id}>
                      <button
                        type="button"
                        className={styles.item}
                        data-unread={item.is_read ? undefined : "true"}
                        onClick={() => openItem(item)}
                      >
                        <span className={styles.itemTitle}>{item.title}</span>
                        {item.body && <span className={styles.itemBody}>{item.body}</span>}
                        <span className={styles.itemMeta}>{formatWhen(item.created_at)}</span>
                      </button>
                    </li>
                  ))}
                </ul>
              )}

              {total > items.length && (
                <p className={styles.panelFooter}>
                  Showing the {items.length} most recent of {total}.
                </p>
              )}
            </div>,
            document.body
          )
        : null}
    </div>
  );
}
