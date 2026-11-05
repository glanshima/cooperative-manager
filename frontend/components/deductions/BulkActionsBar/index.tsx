import type { DeductionActionKind } from "../hooks/useDeductionsPage";

export default function BulkActionsBar({
  count,
  busy,
  onAction,
  onClear,
}: {
  count: number;
  busy: boolean;
  onAction: (action: DeductionActionKind) => void;
  onClear: () => void;
}) {
  if (!count) return null;

  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: 8,
        marginBottom: 12,
        padding: 8,
        background: "#eef4ff",
        borderRadius: 4,
      }}
    >
      <strong>{count} selected</strong>
      <button disabled={busy} onClick={() => onAction("submit")}>
        Submit
      </button>
      <button disabled={busy} onClick={() => onAction("confirm")}>
        Confirm
      </button>
      <button disabled={busy} onClick={() => onAction("not_deducted")}>
        Not deducted
      </button>
      <button disabled={busy} onClick={() => onAction("void")}>
        Void
      </button>
      <button disabled={busy} onClick={onClear} style={{ marginLeft: "auto" }}>
        Clear selection
      </button>
    </div>
  );
}
