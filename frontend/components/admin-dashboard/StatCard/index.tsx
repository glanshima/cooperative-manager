import Link from "next/link";
import type { ReactNode } from "react";

import styles from "./StatCard.module.css";

export default function StatCard({
  label,
  value,
  hint,
  href,
}: {
  label: string;
  value: ReactNode;
  hint?: ReactNode;
  href?: string;
}) {
  const content = (
    <>
      <span className={styles.label}>{label}</span>
      <strong className={styles.value}>{value}</strong>
      {hint ? <span className={styles.hint}>{hint}</span> : null}
    </>
  );

  if (href) {
    return (
      <Link href={href} className={`${styles.card} ${styles.link}`}>
        {content}
      </Link>
    );
  }
  return <div className={styles.card}>{content}</div>;
}
