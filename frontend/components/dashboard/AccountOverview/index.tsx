import { formatMoney } from "@/components/deductions/labels";
import type { MemberLoanBalance, MemberSavings } from "@/lib/api";

import styles from "../dashboard.module.css";

function widthOf(value: number, max: number) {
  if (value <= 0 || max <= 0) return 0;
  return Math.max(3, Math.round((value / max) * 100));
}

/** Savings against what the member still owes. Both are server reads, and
 *  the bars only compare them to each other -- they are not a ratio. */
export default function AccountOverview({
  savings,
  loanBalance,
  loansEnabled,
}: {
  savings: MemberSavings | null;
  loanBalance: MemberLoanBalance | null;
  loansEnabled: boolean;
}) {
  const saved = savings ? Number(savings.savings_balance) : null;
  const owed =
    loansEnabled && loanBalance ? Number(loanBalance.total_outstanding_balance) : null;
  const max = Math.max(saved ?? 0, owed ?? 0);

  return (
    <section className={styles.panel}>
      <div className={styles.panelHead}>
        <h2 className={styles.panelTitle}>Account overview</h2>
        {saved !== null && (
          <p className={styles.panelNote}>
            {saved > 0 && owed !== null
              ? saved >= owed
                ? "Savings cover your loan balance"
                : "Loan balance is larger than your savings"
              : ""}
          </p>
        )}
      </div>

      {saved === null && owed === null ? (
        <p className={styles.empty}>Your figures could not be loaded just now.</p>
      ) : (
        <div className={styles.compare}>
          <div className={styles.compareRow}>
            <div className={styles.compareHead}>
              <span className={styles.compareLabel}>Savings</span>
              <span className={styles.compareValue}>
                {saved === null ? "Unavailable" : `₦${formatMoney(saved)}`}
              </span>
            </div>
            <div className={styles.track}>
              <div
                className={`${styles.bar} ${styles.barSavings}`}
                style={{ width: `${widthOf(saved ?? 0, max)}%` }}
              />
            </div>
          </div>

          {loansEnabled && (
            <div className={styles.compareRow}>
              <div className={styles.compareHead}>
                <span className={styles.compareLabel}>Outstanding loan</span>
                <span className={styles.compareValue}>
                  {owed === null ? "Unavailable" : `₦${formatMoney(owed)}`}
                </span>
              </div>
              <div className={styles.track}>
                <div
                  className={`${styles.bar} ${styles.barLoans}`}
                  style={{ width: `${widthOf(owed ?? 0, max)}%` }}
                />
              </div>
            </div>
          )}

          <p className={styles.compareFoot}>
            Savings counts confirmed monthly savings only.
            {loansEnabled
              ? " The loan balance is computed by the cooperative across your active loans."
              : ""}
          </p>
        </div>
      )}
    </section>
  );
}
