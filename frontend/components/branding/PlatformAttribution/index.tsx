import { PLATFORM_NAME } from "@/lib/branding";

import styles from "./PlatformAttribution.module.css";

interface PlatformAttributionProps {
  tone?: "default" | "inverse";
}

// Discreet platform credit. The cooperative's own identity stays primary;
// this marks the software without competing with it.
export default function PlatformAttribution({
  tone = "default",
}: PlatformAttributionProps) {
  return (
    <p
      className={`${styles.attribution} ${tone === "inverse" ? styles.inverse : ""}`}
    >
      <span>Powered by</span>
      <img src="/brand/koperra-symbol.svg" alt="" className={styles.symbol} />
      <span className={styles.name}>{PLATFORM_NAME}</span>
    </p>
  );
}
