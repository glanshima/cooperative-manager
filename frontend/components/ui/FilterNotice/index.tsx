import type { ReactNode } from "react";

// A queue link from the dashboard opens its page already filtered. This
// line says which slice is shown and offers the way back to the full list.
export default function FilterNotice({
  children,
  onClear,
}: {
  children: ReactNode;
  onClear: () => void;
}) {
  return (
    <p
      role="status"
      style={{
        margin: "0 0 16px",
        fontSize: 14,
        color: "var(--text-muted)",
      }}
    >
      {children}{" "}
      <button type="button" onClick={onClear} style={{ fontSize: 13 }}>
        Show all
      </button>
    </p>
  );
}
