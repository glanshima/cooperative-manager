import Modal from "@/components/ui/Modal";

/** A deliberate second step before an action that is hard to undo or that
 * changes someone's access. Confirming is not the default focus, so hitting
 * Enter by accident cancels rather than acts. */
export default function ConfirmDialog({
  title,
  message,
  confirmLabel,
  cancelLabel = "Cancel",
  busy = false,
  error,
  onConfirm,
  onCancel,
}: {
  title: string;
  message: string;
  confirmLabel: string;
  cancelLabel?: string;
  busy?: boolean;
  error?: string | null;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  return (
    <Modal
      title={title}
      onClose={onCancel}
      busy={busy}
      closeLabel="Close confirmation"
      testId="confirm-dialog-backdrop"
      maxWidth={440}
    >
      <p style={{ margin: "0 0 12px 0" }}>{message}</p>
      {error && (
        <p role="alert" style={{ margin: "0 0 12px 0", color: "#a33", fontSize: 14 }}>
          {error}
        </p>
      )}
      <div className="toolbar toolbar--end">
        <button type="button" data-initial-focus disabled={busy} onClick={onCancel}>
          {cancelLabel}
        </button>
        <button type="button" disabled={busy} onClick={onConfirm}>
          {busy ? "Working…" : confirmLabel}
        </button>
      </div>
    </Modal>
  );
}
