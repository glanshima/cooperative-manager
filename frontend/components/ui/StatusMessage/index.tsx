import type { CSSProperties, ReactNode } from "react";

const TONE_STYLES: Record<"error" | "success", CSSProperties> = {
  error: { color: "crimson", fontWeight: 600 },
  success: { color: "green", fontWeight: 600 },
};

export default function StatusMessage({
  tone,
  children,
}: {
  tone: "error" | "success";
  children: ReactNode;
}) {
  return <p style={TONE_STYLES[tone]}>{children}</p>;
}
