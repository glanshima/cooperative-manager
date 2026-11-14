"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useRef, useState } from "react";
import type { KeyboardEvent } from "react";

import { useAdminNav } from "../hooks/useAdminNav";
import styles from "./AdminNav.module.css";

const NAV_ID = "admin-navigation";

export default function AdminNav() {
  const { links } = useAdminNav();
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  const menuButtonRef = useRef<HTMLButtonElement>(null);

  function handleKeyDown(event: KeyboardEvent<HTMLElement>) {
    if (event.key === "Escape" && open) {
      event.stopPropagation();
      setOpen(false);
      menuButtonRef.current?.focus();
    }
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
          id={NAV_ID}
          aria-label="Admin"
          className={styles.nav}
          data-open={open ? "true" : undefined}
        >
          <ul className={styles.list}>
            {links.map((link) => {
              const active = pathname === link.href;
              return (
                <li key={link.href}>
                  <Link
                    href={link.href}
                    className={active ? `${styles.link} ${styles.active}` : styles.link}
                    aria-current={active ? "page" : undefined}
                    onClick={() => setOpen(false)}
                  >
                    {link.label}
                  </Link>
                </li>
              );
            })}
          </ul>
        </nav>
      </div>
    </header>
  );
}
