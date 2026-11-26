"use client";

import Link from "next/link";

import { formatMoney } from "@/components/deductions/labels";
import DashboardHeader from "@/components/ui/DashboardHeader";
import StatusMessage from "@/components/ui/StatusMessage";
import { lastNameFirst } from "@/lib/names";
import { hasAnyPermission, hasPermission } from "@/lib/permissions";
import { type DashboardPeriodKey } from "@/lib/api";

import StatCard from "../StatCard";
import TrendChart from "../TrendChart";
import type { AdminDashboardPageModel } from "../hooks/useAdminDashboardPage";
import styles from "./AdminDashboardView.module.css";

const PERIOD_OPTIONS: { key: DashboardPeriodKey; label: string }[] = [
  { key: "this_month", label: "This month" },
  { key: "last_month", label: "Last month" },
  { key: "this_year", label: "This year" },
  { key: "last_year", label: "Last year" },
];

// Mirrors the action permissions the backend uses to decide which work
// queues a caller may see. An empty list is only reassuring when the
// account can act on at least one queue.
const ACTION_PERMISSIONS = [
  "loan.review",
  "disbursement.submit",
  "repayment.verify",
  "loan.fee_verify",
  "deduction.submit",
  "deduction.confirm",
  "savings.settle",
  "dividend.pay",
];

function money(value: string | null | undefined): string {
  return value == null ? "—" : `₦${formatMoney(value)}`;
}

function day(value: string): string {
  return new Date(`${value}T00:00:00`).toLocaleDateString(undefined, {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}

function when(value: string): string {
  return new Date(value).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

export default function AdminDashboardView({ model }: { model: AdminDashboardPageModel }) {
  const { user } = model.auth;
  const data = model.data;
  const headingName = user ? lastNameFirst(user.member_name) ?? user.username : null;

  const canAct = user ? hasAnyPermission(user.permissions, ACTION_PERMISSIONS) : false;
  const hasPeriodFigures = Boolean(
    data && (data.members || data.savings || data.loans || data.deductions)
  );
  const hasSnapshotFigures = Boolean(
    data && (data.members || data.savings || data.loans || data.cashbook || data.dividends)
  );
  const hasMovementFigures = Boolean(
    data && (data.members || data.savings || data.loans || data.deductions)
  );
  const isEmpty =
    !data ||
    (!hasSnapshotFigures &&
      !hasMovementFigures &&
      data.queues.length === 0 &&
      data.activity === null &&
      data.trend === null);

  return (
    <main className="page page--1200">
      <DashboardHeader name={headingName} fallbackTitle="Admin Dashboard" />

      {model.error && (
        <StatusMessage tone="error" onDismiss={model.dismissError} dismissLabel="Dismiss error">
          {data ? "Could not refresh the dashboard" : "Could not load the dashboard"}: {model.error}
          {data ? " — the figures below are from the previous load." : ""}
        </StatusMessage>
      )}

      {!data ? (
        <section className={styles.panel}>
          <p className={styles.empty}>The dashboard could not be loaded.</p>
          <div className={styles.panelActions}>
            <button type="button" onClick={model.reload}>
              Try again
            </button>
          </div>
        </section>
      ) : isEmpty ? (
        <section className={styles.panel}>
          <p className={styles.empty}>
            No dashboard figures are available to this account yet. Module screens remain
            available from the menu; ask an administrator if you expect figures here.
          </p>
        </section>
      ) : (
        <>
          {hasPeriodFigures && (
            <>
              <div className={styles.controls}>
                <div className={styles.periodGroup} role="group" aria-label="Reporting period">
                  {PERIOD_OPTIONS.map((option) => (
                    <button
                      key={option.key}
                      type="button"
                      className={styles.periodButton}
                      aria-pressed={model.period === option.key}
                      onClick={() => model.setPeriod(option.key)}
                    >
                      {option.label}
                    </button>
                  ))}
                </div>
                {model.refreshing && (
                  <span className={styles.updating} aria-live="polite">
                    Updating…
                  </span>
                )}
              </div>
              <p className={styles.caption}>
                Balances are current. Period figures count only transactions dated{" "}
                {day(data.period.start)} – {day(data.period.end)}.
              </p>
            </>
          )}

          {hasSnapshotFigures && (
            <section className={styles.section}>
              <div className={styles.sectionHead}>
                <h2 className={styles.sectionTitle}>At a glance</h2>
              </div>
              <div className={styles.statGrid}>
                {data.members && (
                  <StatCard
                    label="Members"
                    value={data.members.total.toLocaleString()}
                    hint={
                      <>
                        {data.members.financial.toLocaleString()} financial ·{" "}
                        {data.members.non_financial.toLocaleString()} non-financial
                        {data.members.exited > 0
                          ? ` · ${data.members.exited.toLocaleString()} exited`
                          : ""}
                      </>
                    }
                    href="/members"
                  />
                )}
                {data.savings && (
                  <StatCard
                    label="Savings balance"
                    value={money(data.savings.total)}
                    hint="Confirmed savings less reversals and exit payouts"
                  />
                )}
                {data.loans && (
                  <StatCard
                    label="Outstanding loans"
                    value={money(data.loans.outstanding)}
                    hint={
                      <>
                        {data.loans.active_count.toLocaleString()} active · includes interest
                        {data.loans.defaulted_count > 0
                          ? ` · ${data.loans.defaulted_count.toLocaleString()} defaulted`
                          : ""}
                      </>
                    }
                    href="/loans"
                  />
                )}
                {data.cashbook && (
                  <StatCard
                    label="Cash & bank"
                    value={data.cashbook.books_open ? money(data.cashbook.total) : "—"}
                    hint={
                      data.cashbook.books_open
                        ? `Cash ${money(data.cashbook.cash)} · Bank ${money(data.cashbook.bank)}`
                        : "Cashbook books not opened yet"
                    }
                    href="/admin/cashbook"
                  />
                )}
                {data.dividends && (
                  <StatCard
                    label="Dividends unpaid"
                    value={money(data.dividends.unpaid_net)}
                    hint={
                      data.dividends.last_declared_year != null
                        ? `Last declared ${data.dividends.last_declared_year} · pool ${money(
                            data.dividends.last_pool
                          )}`
                        : "No declared run yet"
                    }
                    href="/admin/dividends"
                  />
                )}
              </div>
            </section>
          )}

          {(data.queues.length > 0 || canAct) && (
            <section className={styles.section}>
              <div className={styles.sectionHead}>
                <h2 className={styles.sectionTitle}>Needs attention</h2>
              </div>
              <div className={styles.panel}>
                {data.queues.length === 0 ? (
                  <p className={styles.empty}>Nothing is waiting on you right now.</p>
                ) : (
                  <ul className={styles.queueList}>
                    {data.queues.map((item) => (
                      <li key={item.key} className={styles.queueItem}>
                        <Link href={item.href} className={styles.queueLink}>
                          <span className={styles.queueLabel}>{item.label}</span>
                          <span className={styles.queueMeta}>
                            {item.amount ? <span>{money(item.amount)}</span> : null}
                            <span className={styles.queueCount}>{item.count.toLocaleString()}</span>
                          </span>
                        </Link>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            </section>
          )}

          {hasMovementFigures && (
            <section className={styles.section}>
              <div className={styles.sectionHead}>
                <h2 className={styles.sectionTitle}>{data.period.label}</h2>
              </div>
              <div className={`${styles.statGrid} ${styles.movementGrid}`}>
                {data.members && (
                  <StatCard
                    label="New members"
                    value={data.members.joined.toLocaleString()}
                    hint="Joined in this period"
                  />
                )}
                {data.savings && (
                  <>
                    <StatCard
                      label="Savings collected"
                      value={money(data.savings.collected)}
                      hint="Confirmed savings posted in this period"
                    />
                    <StatCard
                      label="Savings paid out"
                      value={money(data.savings.paid_out)}
                      hint="Exit settlements paid in this period"
                    />
                  </>
                )}
                {data.loans && (
                  <StatCard
                    label="Loans disbursed"
                    value={money(data.loans.disbursed)}
                    hint={`${data.loans.disbursed_count.toLocaleString()} loan${
                      data.loans.disbursed_count === 1 ? "" : "s"
                    } · principal`}
                  />
                )}
                {data.loans?.repayments && (
                  <StatCard
                    label="Repayments verified"
                    value={money(data.loans.repayments.amount)}
                    hint={`${data.loans.repayments.count.toLocaleString()} payment${
                      data.loans.repayments.count === 1 ? "" : "s"
                    }`}
                  />
                )}
                {data.deductions && (
                  <StatCard
                    label="Deductions confirmed"
                    value={money(data.deductions.confirmed_total)}
                    hint={`${data.deductions.confirmed_members.toLocaleString()} member${
                      data.deductions.confirmed_members === 1 ? "" : "s"
                    }`}
                    href="/admin/deductions"
                  />
                )}
              </div>
            </section>
          )}

          {data.trend && (
            <section className={styles.section}>
              <div className={styles.sectionHead}>
                <h2 className={styles.sectionTitle}>Last 6 months</h2>
              </div>
              <div className={styles.panel}>
                <TrendChart trend={data.trend} />
              </div>
            </section>
          )}

          {data.activity && (
            <section className={styles.section}>
              <div className={styles.sectionHead}>
                <h2 className={styles.sectionTitle}>Recent activity</h2>
                {user && hasPermission(user.permissions, "audit.view") && (
                  <Link href="/admin/audit" className={styles.sectionLink}>
                    View audit log
                  </Link>
                )}
              </div>
              <div className={styles.panel}>
                {data.activity.length === 0 ? (
                  <p className={styles.empty}>No activity has been recorded yet.</p>
                ) : (
                  <ul className={styles.activityList}>
                    {data.activity.map((event, index) => (
                      <li key={`${event.timestamp}-${index}`} className={styles.activityItem}>
                        <span>
                          <span className={styles.activityActor}>{event.actor}</span>{" "}
                          {event.event_type.replace(/[._]+/g, " ")}
                        </span>
                        <time className={styles.activityTime} dateTime={event.timestamp}>
                          {when(event.timestamp)}
                        </time>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            </section>
          )}
        </>
      )}
    </main>
  );
}
