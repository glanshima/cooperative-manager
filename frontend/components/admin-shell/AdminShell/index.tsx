import type { ReactNode } from "react";

import AdminNav from "../AdminNav";

export default function AdminShell({ children }: { children: ReactNode }) {
  return (
    <>
      <AdminNav />
      {children}
    </>
  );
}
