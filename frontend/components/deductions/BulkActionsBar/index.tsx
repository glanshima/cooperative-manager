import type { DeductionActionKind } from "../hooks/useDeductionsPage";

const ACTION_HINTS: Record<DeductionActionKind, string> = {
  submit: "Only draft deductions can be submitted.",
  return_to_draft: "Only submitted deductions can be returned to draft.",
  confirm: "Only submitted deductions can be confirmed.",
  not_deducted: "Only draft or submitted deductions can be marked not deducted.",
  void: "Voided deductions cannot be voided again.",
};

const BUTTONS: { action: DeductionActionKind; label: string }[] = [
  { action: "submit", label: "Submit" },
  { action: "confirm", label: "Confirm" },
  { action: "not_deducted", label: "Not deducted" },
  { action: "void", label: "Void" },
];

export default function BulkActionsBar({
  count,
  eligible,
  busy,
  onAction,
  onClear,
}: {
  count: number;
  eligible: Record<DeductionActionKind, number>;
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
      {BUTTONS.map(({ action, label }) => {
        const reachable = eligible[action] ?? 0;
        const partial = reachable > 0 && reachable < count;
        return (
          <button
            key={action}
            disabled={busy || reachable === 0}
            title={reachable === 0 ? ACTION_HINTS[action] : undefined}
            onClick={() => onAction(action)}
          >
            {partial ? `${label} (${reachable})` : label}
          </button>
        );
      })}
      <button disabled={busy} onClick={onClear} style={{ marginLeft: "auto" }}>
        Clear selection
      </button>
    </div>
  );
}
