import Link from "next/link";

import {
  COOPERATIVE_MONOGRAM,
  COOPERATIVE_NAME,
} from "@/lib/branding";

import styles from "./CooperativeBrand.module.css";

interface CooperativeBrandProps {
  name?: string;
  monogram?: string;
  logoUrl?: string | null;
  href?: string;
  tone?: "default" | "inverse";
}

export default function CooperativeBrand({
  name = COOPERATIVE_NAME,
  monogram = COOPERATIVE_MONOGRAM,
  logoUrl = null,
  href,
  tone = "default",
}: CooperativeBrandProps) {
  const content = (
    <>
      {logoUrl ? (
        <img src={logoUrl} alt="" className={styles.logo} />
      ) : (
        <span className={styles.monogram} aria-hidden="true">
          {monogram}
        </span>
      )}
      <span className={styles.name}>{name}</span>
    </>
  );

  const className = `${styles.brand} ${tone === "inverse" ? styles.inverse : ""}`;

  if (href) {
    return (
      <Link href={href} className={className} data-tone={tone}>
        {content}
      </Link>
    );
  }

  return (
    <div className={className} data-tone={tone}>
      {content}
    </div>
  );
}
