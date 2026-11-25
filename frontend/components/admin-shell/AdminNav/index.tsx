"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import CooperativeBrand from "@/components/branding/CooperativeBrand";
import PlatformAttribution from "@/components/branding/PlatformAttribution";
import NotificationBell from "@/components/notifications/NotificationBell";
import LogoutControl from "@/components/ui/LogoutControl";
import { useAuth } from "@/lib/useAuth";
import { useMediaQuery } from "@/lib/useMediaQuery";

import { useAdminNav } from "../hooks/useAdminNav";
import styles from "./AdminNav.module.css";

const SIDEBAR_ID = "admin-sidebar";

function submenuId(label: string) {
  return `admin-submenu-${label.toLowerCase().replace(/[^a-z0-9]+/g, "-")}`;
}

export default function AdminNav() {
  // The shell owns the auth gate: until /me resolves, nothing is rendered,
  // so a member or signed-out visitor never sees a flash of admin chrome
  // before the redirect lands.
  const { user, logout } = useAuth({
    requireAuth: true,
    requirePasswordChanged: true,
    requireRole: "admin",
  });
  const { items } = useAdminNav(user?.permissions ?? []);
  const pathname = usePathname();
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [openGroup, setOpenGroup] = useState<string | null>(null);
  const menuButtonRef = useRef<HTMLButtonElement>(null);
  // Below 900px the sidebar is an off-canvas drawer, so the bell rides in the
  // top bar instead; above it, it shares the brand row with the wordmark.
  const drawerNav = useMediaQuery("(max-width: 900px)");

  const activeGroupLabel = items.find(
    (item) => item.kind === "group" && item.children.some((child) => pathname === child.href)
  )?.label;

  // The section the officer is in stays expanded so the sidebar always shows
  // where they are. Exactly one group is open at a time.
  useEffect(() => {
    setOpenGroup(activeGroupLabel ?? null);
  }, [pathname, activeGroupLabel]);

  useEffect(() => {
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key !== "Escape") return;
      if (drawerOpen) {
        setDrawerOpen(false);
        menuButtonRef.current?.focus();
        return;
      }
      setOpenGroup(null);
    }
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [drawerOpen]);

  // The drawer covers the page, so the page behind it must not scroll.
  useEffect(() => {
    if (!drawerOpen) return;
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = previous;
    };
  }, [drawerOpen]);

  function toggleGroup(label: string) {
    setOpenGroup((current) => (current === label ? null : label));
  }

  function closeDrawer() {
    setDrawerOpen(false);
  }

  function handleNavClick() {
    setDrawerOpen(false);
  }

  if (!user) return null;

  return (
    <>
      <header className={styles.topbar}>
        <CooperativeBrand href="/admin/dashboard" />
        <div className={styles.topbarActions}>
          {drawerNav ? <NotificationBell /> : null}
          <button
            ref={menuButtonRef}
            type="button"
            className={styles.menuButton}
            aria-expanded={drawerOpen}
            aria-controls={SIDEBAR_ID}
            aria-label={drawerOpen ? "Close admin navigation" : "Open admin navigation"}
            onClick={() => setDrawerOpen((current) => !current)}
          >
            <svg
              aria-hidden="true"
              viewBox="0 0 24 24"
              width="20"
              height="20"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
            >
              <path d="M4 6h16M4 12h16M4 18h16" />
            </svg>
          </button>
        </div>
      </header>
      <div
        className={styles.scrim}
        data-open={drawerOpen ? "true" : undefined}
        onClick={closeDrawer}
        aria-hidden="true"
      />
      <aside
        id={SIDEBAR_ID}
        className={styles.sidebar}
        aria-label="Admin sidebar"
        data-open={drawerOpen ? "true" : undefined}
      >
        <div className={styles.brandRow}>
          <CooperativeBrand href="/admin/dashboard" tone="inverse" />
          <div className={styles.brandActions}>
            {drawerNav ? null : <NotificationBell tone="inverse" />}
            <button
              type="button"
              className={styles.closeButton}
              aria-label="Close menu"
              onClick={closeDrawer}
            >
              ×
            </button>
          </div>
        </div>
        <nav aria-label="Admin" className={styles.nav}>
          <ul className={styles.list}>
            {items.map((item) => {
              if (item.kind === "link") {
                const active = pathname === item.href;
                return (
                  <li key={item.href}>
                    <Link
                      href={item.href}
                      className={active ? `${styles.link} ${styles.active}` : styles.link}
                      aria-current={active ? "page" : undefined}
                      onClick={handleNavClick}
                    >
                      {item.label}
                    </Link>
                  </li>
                );
              }

              const id = submenuId(item.label);
              const expanded = openGroup === item.label;
              const groupActive = item.children.some((child) => pathname === child.href);
              return (
                <li
                  key={item.label}
                  className={styles.group}
                  data-open={expanded ? "true" : undefined}
                >
                  <button
                    type="button"
                    className={styles.groupButton}
                    data-active={groupActive ? "true" : undefined}
                    aria-expanded={expanded}
                    aria-controls={id}
                    onClick={() => toggleGroup(item.label)}
                  >
                    {item.label}
                    <span className={styles.caret} aria-hidden="true">
                      ▾
                    </span>
                  </button>
                  <ul id={id} className={styles.submenu}>
                    {item.children.map((child) => {
                      const active = pathname === child.href;
                      return (
                        <li key={child.href}>
                          <Link
                            href={child.href}
                            className={active ? `${styles.link} ${styles.active}` : styles.link}
                            aria-current={active ? "page" : undefined}
                            onClick={handleNavClick}
                          >
                            {child.label}
                          </Link>
                        </li>
                      );
                    })}
                  </ul>
                </li>
              );
            })}
          </ul>
        </nav>
        <div className={styles.account}>
          <LogoutControl
            variant="sidebar"
            identity={user?.username ?? null}
            onLogout={logout}
          />
        </div>
        <footer className={styles.footer}>
          <PlatformAttribution tone="inverse" />
        </footer>
      </aside>
    </>
  );
}
