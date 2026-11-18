import styles from "./PageSkeleton.module.css";

export default function PageSkeleton() {
  return (
    <main className="page page--1100" role="status" aria-live="polite" aria-busy="true">
      <span className={styles.srOnly}>Loading page content</span>
      <div className={styles.header} aria-hidden="true">
        <span className={`skeleton ${styles.title}`} />
        <span className={`skeleton ${styles.action}`} />
      </div>
      <div className={styles.cards} aria-hidden="true">
        <span className={`skeleton ${styles.card}`} />
        <span className={`skeleton ${styles.card}`} />
        <span className={`skeleton ${styles.card}`} />
      </div>
      <span className={`skeleton ${styles.table}`} aria-hidden="true" />
    </main>
  );
}
