import { formatMoney } from "@/components/deductions/labels";
import type { Member } from "@/lib/api";

import DashboardIcon from "../icons";
import styles from "../dashboard.module.css";

function monthYear(value: string | null | undefined) {
  if (!value) return null;
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? null
    : date.toLocaleDateString(undefined, { month: "long", year: "numeric" });
}

function maskedAccount(number: string | null | undefined) {
  const digits = number?.replace(/\s+/g, "") ?? "";
  return digits.length >= 4 ? `•••• ${digits.slice(-4)}` : null;
}

export default function MembershipCard({ member }: { member: Member }) {
  const exited = Boolean(member.membership_exit_date);
  const financial = member.status === "financial";
  const label = exited
    ? "Membership ended"
    : financial
    ? "Financial member"
    : "Non-financial member";
  const since = exited
    ? `Exited ${monthYear(member.membership_exit_date) ?? ""}`.trim()
    : `Member since ${monthYear(member.created_at) ?? "—"}`;

  const bank = member.bank_name
    ? [member.bank_name, maskedAccount(member.account_number)].filter(Boolean).join(" · ")
    : "—";

  return (
    <section className={styles.panel}>
      <div className={styles.panelHead}>
        <h2 className={styles.panelTitle}>Your membership</h2>
      </div>

      <div className={styles.statusRow}>
        <span className={`${styles.statusIcon} ${financial && !exited ? "" : styles.statusIconMuted}`}>
          <DashboardIcon name="check" size={17} />
        </span>
        <div>
          <p className={styles.statusLabel}>{label}</p>
          <p className={styles.statusSince}>{since}</p>
        </div>
      </div>

      <dl className={styles.detailList}>
        <div className={styles.detailRow}>
          <dt className={styles.detailTerm}>Monthly savings</dt>
          <dd className={styles.detailValue}>
            {member.monthly_contribution_amount
              ? `₦${formatMoney(member.monthly_contribution_amount)}`
              : "Not set"}
          </dd>
        </div>
        <div className={styles.detailRow}>
          <dt className={styles.detailTerm}>Department</dt>
          <dd className={styles.detailValue}>{member.department || "—"}</dd>
        </div>
        <div className={styles.detailRow}>
          <dt className={styles.detailTerm}>Payout account</dt>
          <dd className={styles.detailValue}>{bank}</dd>
        </div>
      </dl>

      {member.loan_restricted && (
        <p className={`${styles.chip} ${styles.chipDanger}`}>
          Loans restricted{member.restriction_reason ? ` · ${member.restriction_reason}` : ""}
        </p>
      )}
    </section>
  );
}
