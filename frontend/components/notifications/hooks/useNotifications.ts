"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import {
  getNotifications,
  markAllNotificationsRead,
  markNotificationRead,
  type Notification,
} from "@/lib/api";

const POLL_MS = 60_000;
const PANEL_LIMIT = 20;

/**
 * The bell's data source: the newest notices plus the unread badge, kept
 * fresh on mount, on open and on a slow poll. Mutations update the local
 * state optimistically and fall back to the next poll if a call fails.
 */
export function useNotifications() {
  const [items, setItems] = useState<Notification[]>([]);
  const [unreadCount, setUnreadCount] = useState(0);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const mounted = useRef(true);

  const refresh = useCallback(async () => {
    try {
      const page = await getNotifications({ limit: PANEL_LIMIT });
      if (!mounted.current) return;
      setItems(page.items);
      setUnreadCount(page.unread_count);
      setTotal(page.total);
      setError(null);
    } catch {
      if (mounted.current) setError("Notifications could not be loaded.");
    } finally {
      if (mounted.current) setLoading(false);
    }
  }, []);

  useEffect(() => {
    mounted.current = true;
    refresh();
    const timer = setInterval(refresh, POLL_MS);
    return () => {
      mounted.current = false;
      clearInterval(timer);
    };
  }, [refresh]);

  const markRead = useCallback(async (id: string) => {
    setItems((current) =>
      current.map((item) =>
        item.id === id
          ? { ...item, is_read: true, read_at: item.read_at ?? new Date().toISOString() }
          : item
      )
    );
    setUnreadCount((current) => Math.max(0, current - 1));
    try {
      await markNotificationRead(id);
    } catch {
      // The next poll reconciles the badge with the server.
    }
  }, []);

  const markAllRead = useCallback(async () => {
    setItems((current) => current.map((item) => ({ ...item, is_read: true })));
    setUnreadCount(0);
    try {
      await markAllNotificationsRead();
    } catch {
      refresh();
    }
  }, [refresh]);

  return {
    items,
    unreadCount,
    total,
    loading,
    error,
    refresh,
    markRead,
    markAllRead,
  };
}
