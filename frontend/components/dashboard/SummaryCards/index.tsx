import { formatMoney } from "@/components/deductions/labels";
import type { MemberDeductions, MemberLoanBalance, MemberSavings } from "@/lib/api";
import { monthLabel } from "@/lib/month";

import DashboardIcon from "../icons";
import styles from "../dashboard.module.css";

const STATUS: Record<
  NonNullable<MemberDeductions["status"]>,
  { label: string; tone: string }
> = {
  confirmed: { label: "Confirmed", tone: styles.chipConfirmed },
  submitted: { label: "Submitted", tone: styles.chipPending },
  draft: { label: "Draft", tone: styles.chipMuted },
  not_deducted: { label: "Not deducted", tone: styles.chipMuted },
};

/** The three figures a member checks first: what they have saved, what they
 *  still owe, and what payroll is holding back this month. Every number is a
 *  server read; null renders as "Unavailable", never as zero. */
export default function SummaryCards({
  savings,
  loanBalance,
  deductions,
  loansEnabled,
  deductionsEnabled,
}: {
  savings: MemberSavings | null;
  loanBalance: MemberLoanBalance | null;
  deductions: MemberDeductions | null;
  loansEnabled: boolean;
  deductionsEnabled: boolean;
}) {
  const months = savings?.months_contributed ?? 0;
  const activeLoans = loanBalance?.active_loan_count ?? 0;
  const status = deductions?.status ? STATUS[deductions.status] : null;

  return (
    <div className={styles.statGrid}>
      <section className={`${styles.statCard} ${styles.statCardSavings}`}>
        <span className={styles.statIcon}>
          <DashboardIcon name="savings" size={20} />
        </span>
        <div className={styles.statBody}>
          <h2 className={styles.statLabel}>Total savings</h2>
          {savings ? (
            <>
              <p className={styles.statValue}>₦{formatMoney(savings.savings_balance)}</p>
              <p className={styles.statHint}>
                {months === 0
                  ? "No confirmed savings yet"
                  : `Across ${months} confirmed month${months === 1 ? "" : "s"}`}
              </p>
            </>
          ) : (
            <>
              <p className={styles.statValueMuted}>Unavailable</p>
              <p className={styles.statHint}>Savings could not be loaded just now.</p>
            </>
          )}
          <a className={styles.statLink} href="#savings">
            View savings
          </a>
        </div>
      </section>

      <section className={`${styles.statCard} ${styles.statCardLoans}`}>
        <span className={styles.statIcon}>
          <DashboardIcon name="loans" size={20} />
        </span>
        <div className={styles.statBody}>
          <h2 className={styles.statLabel}>Outstanding loan</h2>
          {!loansEnabled ? (
            <>
              <p className={styles.statValueMuted}>Loans are disabled</p>
              <p className={styles.statHint}>An administrator turned the module off.</p>
            </>
          ) : loanBalance ? (
            <>
              <p className={styles.statValue}>
                ₦{formatMoney(loanBalance.total_outstanding_balance)}
              </p>
              <p className={styles.statHint}>
                {activeLoans === 0
                  ? "No active loans"
                  : `${activeLoans} active loan${activeLoans === 1 ? "" : "s"}`}
              </p>
              <a className={styles.statLink} href="#loans">
                View loans
              </a>
            </>
          ) : (
            <>
              <p className={styles.statValueMuted}>Unavailable</p>
              <p className={styles.statHint}>Your loan balance could not be loaded just now.</p>
            </>
          )}
        </div>
      </section>

      <section className={`${styles.statCard} ${styles.statCardDeductions}`}>
        <span className={styles.statIcon}>
          <DashboardIcon name="contribution" size={20} />
        </span>
        <div className={styles.statBody}>
          <h2 className={styles.statLabel}>This month&apos;s deduction</h2>
          {!deductionsEnabled ? (
            <>
              <p className={styles.statValueMuted}>Deductions are disabled</p>
              <p className={styles.statHint}>An administrator turned the module off.</p>
            </>
          ) : deductions ? (
            <>
              <p className={styles.statValue}>₦{formatMoney(deductions.total)}</p>
              <span className={`${styles.chip} ${status?.tone ?? styles.chipMuted}`}>
                {status?.label ?? "Not deducted"}
              </span>
              <p className={styles.statHint}>
                {monthLabel(deductions.month)}
                {Number(deductions.total) > 0
                  ? ` · ₦${formatMoney(deductions.contribution)} to savings`
                  : ""}
              </p>
            </>
          ) : (
            <>
              <p className={styles.statValueMuted}>Unavailable</p>
              <p className={styles.statHint}>This month&apos;s deduction could not be loaded.</p>
            </>
          )}
        </div>
      </section>
    </div>
  );
}
