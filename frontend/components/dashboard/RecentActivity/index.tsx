import { formatMoney } from "@/components/deductions/labels";

import type { DashboardActivityItem } from "../hooks/useDashboardPage";
import styles from "../dashboard.module.css";

const GOOD = new Set(["confirmed", "verified", "approved", "disbursed", "paid", "active"]);
const WAITING = new Set(["pending", "submitted", "draft", "under_review"]);
const BAD = new Set(["rejected", "void", "voided", "cancelled", "defaulted"]);

function toneOf(status: string) {
  if (GOOD.has(status)) return styles.chipConfirmed;
  if (WAITING.has(status)) return styles.chipPending;
  if (BAD.has(status)) return styles.chipDanger;
  return styles.chipMuted;
}

function labelOf(status: string) {
  return status.charAt(0).toUpperCase() + status.slice(1).replace(/_/g, " ");
}

function dayOf(value: string) {
  // Date-only fields are calendar days, not instants; parse them in local
  // time so a UTC offset never moves the record to the previous day.
  const iso =
    value.length === 10
      ? `${value}T00:00:00`
      : /[zZ]|[+-]\d{2}:?\d{2}$/.test(value)
      ? value
      : `${value}Z`;
  const date = new Date(iso);
  return Number.isNaN(date.getTime())
    ? value
    : date.toLocaleDateString(undefined, { day: "numeric", month: "short" });
}

const AMOUNT_TONE: Record<DashboardActivityItem["direction"], string> = {
  received: styles.amountIn,
  paid: styles.amountOut,
  requested: styles.amountNeutral,
};

const AMOUNT_SIGN: Record<DashboardActivityItem["direction"], string> = {
  received: "+",
  paid: "−",
  requested: "",
};

export default function RecentActivity({ items }: { items: DashboardActivityItem[] }) {
  return (
    <section id="activity" className={`${styles.panel} ${styles.anchor}`}>
      <div className={styles.panelHead}>
        <h2 className={styles.panelTitle}>Recent activity</h2>
        <p className={styles.panelNote}>Latest loan records</p>
      </div>

      {items.length === 0 ? (
        <p className={styles.empty}>Nothing has happened on your loans yet.</p>
      ) : (
        <ul className={styles.activity}>
          {items.map((item) => (
            <li key={item.id} className={styles.activityItem}>
              <div className={styles.activityMain}>
                <span className={styles.activityDate}>{dayOf(item.date)}</span>
                <span className={styles.activityTitle}>{item.title}</span>
                {item.detail && <span className={styles.activityDetail}>{item.detail}</span>}
              </div>
              <span className={`${styles.activityAmount} ${AMOUNT_TONE[item.direction]}`}>
                {AMOUNT_SIGN[item.direction]}₦{formatMoney(item.amount)}
              </span>
              {item.status && (
                <span className={`${styles.chip} ${styles.activityStatus} ${toneOf(item.status)}`}>
                  {labelOf(item.status)}
                </span>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
