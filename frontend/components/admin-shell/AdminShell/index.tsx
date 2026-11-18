import type { ReactNode } from "react";

import AdminNav from "../AdminNav";

import styles from "./AdminShell.module.css";

export default function AdminShell({ children }: { children: ReactNode }) {
  return (
    <div className={styles.shell}>
      <AdminNav />
      <div className={styles.content}>{children}</div>
    </div>
  );
}
