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
    <div
      role="dialog"
      aria-modal="true"
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(0, 0, 0, 0.45)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: 16,
      }}
    >
      <div style={{ background: "white", padding: 20, borderRadius: 6, maxWidth: 520, width: "100%" }}>
        <h2 style={{ marginTop: 0 }}>{title}</h2>
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
        <div style={{ display: "flex", gap: 8, marginTop: 12 }}>
          <button disabled={busy} onClick={onConfirm}>
            Confirm
          </button>
          <button disabled={busy} onClick={onCancel}>
            Cancel
          </button>
        </div>
      </div>
    </div>
  );
}
