import type { ReactNode } from "react";

import CooperativeBrand from "../CooperativeBrand";
import PlatformAttribution from "../PlatformAttribution";

import styles from "./AuthShell.module.css";

export default function AuthShell({ children }: { children: ReactNode }) {
  return (
    <main className={styles.page}>
      <div className="auth-card">
        <div className={styles.brand}>
          <CooperativeBrand />
        </div>
        {children}
      </div>
      <footer className={styles.footer}>
        <PlatformAttribution />
      </footer>
    </main>
  );
}
