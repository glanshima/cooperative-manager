import Modal from "@/components/ui/Modal";

export default function ReasonDialog({
  title,
  description,
  reason,
  setReason,
  onConfirm,
  onCancel,
  busy,
}: {
  title: string;
  description: string;
  reason: string;
  setReason: (value: string) => void;
  onConfirm: () => void;
  onCancel: () => void;
  busy: boolean;
}) {
  return (
    <Modal title={title} onClose={onCancel} busy={busy} closeLabel="Close reason dialog" maxWidth={520}>
      <p style={{ color: "#444" }}>{description}</p>
      <label>
        <span style={{ display: "block", fontSize: 13, marginBottom: 4 }}>Reason</span>
        <textarea
          aria-label="Reason"
          rows={3}
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          style={{ width: "100%" }}
        />
      </label>
      <div className="toolbar" style={{ marginTop: 12 }}>
        <button disabled={busy} onClick={onConfirm}>
          Confirm
        </button>
        <button disabled={busy} onClick={onCancel}>
          Cancel
        </button>
      </div>
    </Modal>
  );
}
