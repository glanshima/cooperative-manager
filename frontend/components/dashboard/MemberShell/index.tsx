"use client";

import type { ReactNode } from "react";

import CooperativeBrand from "@/components/branding/CooperativeBrand";
import NotificationBell from "@/components/notifications/NotificationBell";
import LogoutControl from "@/components/ui/LogoutControl";
import type { CurrentUser, Member } from "@/lib/api";
import { userDisplayName } from "@/lib/names";
import { useMediaQuery } from "@/lib/useMediaQuery";

import DashboardIcon from "../icons";
import type { DashboardIconName } from "../icons";
import styles from "../dashboard.module.css";

const SECTIONS: Array<{ href: string; label: string; icon: DashboardIconName }> = [
  { href: "#overview", label: "Overview", icon: "overview" },
  { href: "#savings", label: "Savings", icon: "contribution" },
  { href: "#loans", label: "Loans", icon: "loans" },
  { href: "#activity", label: "Activity", icon: "activity" },
  { href: "#notifications", label: "Notifications", icon: "notifications" },
];

// The dashboard is one page, so the rail is a set of in-page section links;
// Overview stays marked as the current view.
const IN_PAGE = SECTIONS.slice(0, 4);

function initialsOf(name: string | null | undefined, fallback: string) {
  const source = name?.trim() || fallback;
  const words = source.split(/[^A-Za-z]+/).filter(Boolean);
  if (words.length === 0) return "?";
  if (words.length === 1) return words[0].slice(0, 2).toUpperCase();
  return (words[0][0] + words[1][0]).toUpperCase();
}

export default function MemberShell({
  member,
  user,
  onLogout,
  children,
}: {
  member: Member | null;
  user: CurrentUser | null;
  onLogout: () => void;
  children: ReactNode;
}) {
  // The brand lives in the sidebar on wide screens and in the top bar on
  // phones, never both, so the cooperative's name is announced once.
  const compact = useMediaQuery("(max-width: 899px)");
  const identity = member?.name ?? userDisplayName(user);
  const psn = member?.psn?.replace(/^MCT-/, "");
  const initials = initialsOf(member?.name, user?.username ?? "");

  return (
    <div className={styles.shell}>
      <aside className={styles.sidebar}>
        {!compact && (
          <div className={styles.sidebarBrand}>
            <CooperativeBrand href="/dashboard" tone="inverse" />
          </div>
        )}
        <p className={styles.tagline}>Member portal</p>
        <nav className={styles.nav} aria-label="Dashboard sections">
          <ul className={styles.navList}>
            {SECTIONS.map((section, index) => (
              <li key={section.href}>
                <a
                  href={section.href}
                  className={`${styles.navLink} ${index === 0 ? styles.navLinkActive : ""}`}
                  aria-current={index === 0 ? "page" : undefined}
                >
                  <span className={styles.navIcon}>
                    <DashboardIcon name={section.icon} />
                  </span>
                  {section.label}
                </a>
              </li>
            ))}
          </ul>
        </nav>
      </aside>

      <div className={styles.main}>
        <header className={styles.topbar}>
          {compact ? (
            <div className={styles.topbarBrand}>
              <CooperativeBrand href="/dashboard" />
            </div>
          ) : (
            <p className={styles.topbarTagline}>Member dashboard</p>
          )}
          <div className={styles.account}>
            <NotificationBell />
            <span className={styles.avatar} aria-hidden="true">
              {initials}
            </span>
            <span className={styles.accountText}>
              <span className={styles.accountName}>{identity ?? "Member"}</span>
              {psn ? <span className={styles.accountRole}>PSN {psn}</span> : null}
            </span>
            <LogoutControl onLogout={onLogout} />
          </div>
        </header>

        {children}

        <nav className={styles.bottomNav} aria-label="Dashboard shortcuts">
          {IN_PAGE.map((section) => (
            <a key={section.href} href={section.href} className={styles.bottomLink}>
              <DashboardIcon name={section.icon} size={20} />
              {section.label}
            </a>
          ))}
        </nav>
      </div>
    </div>
  );
}
