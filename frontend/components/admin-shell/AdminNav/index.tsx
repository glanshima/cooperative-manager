"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import type { KeyboardEvent, MouseEvent as ReactMouseEvent } from "react";

import { useAdminNav } from "../hooks/useAdminNav";
import styles from "./AdminNav.module.css";

const NAV_ID = "admin-navigation";
// Each page renders its own AdminShell, so the nav remounts on navigation and
// component state cannot remember that a menu was dismissed on the way in.
const DISMISSED_PATH_KEY = "admin-nav-dismissed-path";

function submenuId(label: string) {
  return `admin-submenu-${label.toLowerCase().replace(/[^a-z0-9]+/g, "-")}`;
}

function readDismissedPath(): string | null {
  try {
    return window.sessionStorage.getItem(DISMISSED_PATH_KEY);
  } catch {
    return null;
  }
}

function rememberDismissal(path: string) {
  try {
    window.sessionStorage.setItem(DISMISSED_PATH_KEY, path);
  } catch {
    // Without storage the menu still closes for the current page.
  }
}

function clearDismissal() {
  try {
    window.sessionStorage.removeItem(DISMISSED_PATH_KEY);
  } catch {
    // Nothing to clear.
  }
}

export default function AdminNav() {
  const { items } = useAdminNav();
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  const [openGroup, setOpenGroup] = useState<string | null>(null);
  const navRef = useRef<HTMLElement>(null);
  const menuButtonRef = useRef<HTMLButtonElement>(null);
  const pointerType = useRef("mouse");

  const activeGroupLabel = items.find(
    (item) => item.kind === "group" && item.children.some((child) => pathname === child.href)
  )?.label;

  // Landing on a sub-page opens its menu, so the section the officer is in
  // is visible without an extra click. A page they just navigated to through
  // the menu stays closed: following an item means they are done choosing.
  useEffect(() => {
    const dismissed = readDismissedPath();
    if (dismissed && dismissed !== pathname) clearDismissal();
    if (dismissed === pathname) return;
    setOpenGroup(activeGroupLabel ?? null);
  }, [pathname, activeGroupLabel]);

  // Clicking outside the navigation dismisses an open dropdown.
  useEffect(() => {
    if (!openGroup) return;
    function handlePointerDown(event: MouseEvent) {
      if (!navRef.current?.contains(event.target as Node)) setOpenGroup(null);
    }
    document.addEventListener("mousedown", handlePointerDown);
    return () => document.removeEventListener("mousedown", handlePointerDown);
  }, [openGroup]);

  function toggleGroup(label: string, event: ReactMouseEvent<HTMLButtonElement>) {
    // With a mouse, hover owns the submenu: a click keeps it open and moving
    // away closes it. Touch and keyboard clicks toggle.
    if (event.detail !== 0 && pointerType.current === "mouse") {
      setOpenGroup(label);
      return;
    }
    setOpenGroup((current) => (current === label ? null : label));
  }

  function closeNav() {
    setOpen(false);
    setOpenGroup(null);
  }

  function handleNavClick(href: string) {
    if (href !== pathname) rememberDismissal(href);
    closeNav();
  }

  function handleKeyDown(event: KeyboardEvent<HTMLElement>) {
    if (event.key !== "Escape") return;
    if (open) {
      event.stopPropagation();
      closeNav();
      menuButtonRef.current?.focus();
      return;
    }
    if (openGroup) setOpenGroup(null);
  }

  return (
    <header className={styles.header} onKeyDown={handleKeyDown}>
      <div className={styles.bar}>
        <Link href="/admin/dashboard" className={styles.brand}>
          MACT Admin
        </Link>
        <button
          ref={menuButtonRef}
          type="button"
          className={styles.menuButton}
          aria-expanded={open}
          aria-controls={NAV_ID}
          aria-label={open ? "Close admin navigation" : "Open admin navigation"}
          onClick={() => setOpen((current) => !current)}
        >
          Menu
        </button>
        <nav
          ref={navRef}
          id={NAV_ID}
          aria-label="Admin"
          className={styles.nav}
          data-open={open ? "true" : undefined}
        >
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
                      onClick={() => handleNavClick(item.href)}
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
                  onPointerEnter={(event) => {
                    // Touch taps also fire pointerenter; hover is for mice.
                    pointerType.current = event.pointerType || "mouse";
                    if (event.pointerType !== "touch") setOpenGroup(item.label);
                  }}
                  onPointerLeave={(event) => {
                    pointerType.current = event.pointerType || "mouse";
                    if (event.pointerType !== "touch") {
                      setOpenGroup((current) => (current === item.label ? null : current));
                    }
                  }}
                >
                  <button
                    type="button"
                    className={styles.groupButton}
                    data-active={groupActive ? "true" : undefined}
                    aria-expanded={expanded}
                    aria-controls={id}
                    onClick={(event) => toggleGroup(item.label, event)}
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
                            onClick={() => handleNavClick(child.href)}
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
      </div>
    </header>
  );
}
