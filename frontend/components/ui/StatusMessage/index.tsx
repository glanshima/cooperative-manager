import type { CSSProperties, ReactNode } from "react";

const TONE_STYLES: Record<"error" | "success", CSSProperties> = {
  error: { color: "crimson", fontWeight: 600 },
  success: { color: "green", fontWeight: 600 },
};

export default function StatusMessage({
  tone,
  children,
  onDismiss,
  dismissLabel,
}: {
  tone: "error" | "success";
  children: ReactNode;
  onDismiss?: () => void;
  dismissLabel?: string;
}) {
  return (
    <p style={TONE_STYLES[tone]} role={tone === "error" ? "alert" : "status"}>
      {children}
      {onDismiss ? (
        <button
          type="button"
          onClick={onDismiss}
          aria-label={dismissLabel ?? "Dismiss message"}
          style={{ marginLeft: 8, fontSize: 12, fontWeight: 400 }}
        >
          Dismiss
        </button>
      ) : null}
    </p>
  );
}
