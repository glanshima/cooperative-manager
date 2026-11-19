"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import CooperativeBrand from "@/components/branding/CooperativeBrand";
import PlatformAttribution from "@/components/branding/PlatformAttribution";
import LogoutControl from "@/components/ui/LogoutControl";
import { useAuth } from "@/lib/useAuth";

import { useAdminNav } from "../hooks/useAdminNav";
import styles from "./AdminNav.module.css";

const SIDEBAR_ID = "admin-sidebar";

function submenuId(label: string) {
  return `admin-submenu-${label.toLowerCase().replace(/[^a-z0-9]+/g, "-")}`;
}

export default function AdminNav() {
  const { items } = useAdminNav();
  const { user, logout } = useAuth();
  const pathname = usePathname();
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [openGroup, setOpenGroup] = useState<string | null>(null);
  const menuButtonRef = useRef<HTMLButtonElement>(null);

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

  return (
    <>
      <header className={styles.topbar}>
        <CooperativeBrand href="/admin/dashboard" />
        <button
          ref={menuButtonRef}
          type="button"
          className={styles.menuButton}
          aria-expanded={drawerOpen}
          aria-controls={SIDEBAR_ID}
          aria-label={drawerOpen ? "Close admin navigation" : "Open admin navigation"}
          onClick={() => setDrawerOpen((current) => !current)}
        >
          Menu
        </button>
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
          <button
            type="button"
            className={styles.closeButton}
            aria-label="Close menu"
            onClick={closeDrawer}
          >
            ×
          </button>
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
