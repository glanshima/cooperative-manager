"use client";

import Link from "next/link";

import { useBranding } from "../BrandingProvider";

import styles from "./CooperativeBrand.module.css";

interface CooperativeBrandProps {
  name?: string;
  monogram?: string;
  /** Pass null to force the monogram even when a logo is configured. */
  logoUrl?: string | null;
  href?: string;
  tone?: "default" | "inverse";
}

export default function CooperativeBrand({
  name,
  monogram,
  logoUrl,
  href,
  tone = "default",
}: CooperativeBrandProps) {
  const { branding } = useBranding();
  const displayName = name ?? branding.cooperative_name;
  const displayMonogram = monogram ?? branding.cooperative_monogram;
  const displayLogo = logoUrl === undefined ? branding.logo_url : logoUrl;

  const content = (
    <>
      {displayLogo ? (
        <img src={displayLogo} alt="" className={styles.logo} />
      ) : (
        <span className={styles.monogram} aria-hidden="true">
          {displayMonogram}
        </span>
      )}
      <span className={styles.name}>{displayName}</span>
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
