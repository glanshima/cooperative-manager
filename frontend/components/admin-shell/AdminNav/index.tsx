"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import type { KeyboardEvent } from "react";

import { useAdminNav } from "../hooks/useAdminNav";
import styles from "./AdminNav.module.css";

const NAV_ID = "admin-navigation";

function submenuId(label: string) {
  return `admin-submenu-${label.toLowerCase().replace(/[^a-z0-9]+/g, "-")}`;
}

export default function AdminNav() {
  const { items } = useAdminNav();
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  const [openGroups, setOpenGroups] = useState<string[]>([]);
  const navRef = useRef<HTMLElement>(null);
  const menuButtonRef = useRef<HTMLButtonElement>(null);

  const activeGroupLabel = items.find(
    (item) => item.kind === "group" && item.children.some((child) => pathname === child.href)
  )?.label;

  // Landing on a sub-page opens its menu, so the section the officer is in
  // is visible without an extra click.
  useEffect(() => {
    if (!activeGroupLabel) return;
    setOpenGroups((current) =>
      current.includes(activeGroupLabel) ? current : [...current, activeGroupLabel]
    );
  }, [activeGroupLabel]);

  // Clicking outside the navigation dismisses an open dropdown.
  useEffect(() => {
    if (openGroups.length === 0) return;
    function handlePointerDown(event: MouseEvent) {
      if (!navRef.current?.contains(event.target as Node)) setOpenGroups([]);
    }
    document.addEventListener("mousedown", handlePointerDown);
    return () => document.removeEventListener("mousedown", handlePointerDown);
  }, [openGroups.length]);

  function toggleGroup(label: string) {
    setOpenGroups((current) =>
      current.includes(label) ? current.filter((l) => l !== label) : [...current, label]
    );
  }

  function closeNav() {
    setOpen(false);
    setOpenGroups([]);
  }

  function handleKeyDown(event: KeyboardEvent<HTMLElement>) {
    if (event.key !== "Escape") return;
    if (open) {
      event.stopPropagation();
      closeNav();
      menuButtonRef.current?.focus();
      return;
    }
    if (openGroups.length > 0) setOpenGroups([]);
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
                      onClick={closeNav}
                    >
                      {item.label}
                    </Link>
                  </li>
                );
              }

              const id = submenuId(item.label);
              const expanded = openGroups.includes(item.label);
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
                            onClick={closeNav}
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
