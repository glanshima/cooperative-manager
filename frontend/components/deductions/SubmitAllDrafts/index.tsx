import type { DeductionsPageModel } from "../hooks/useDeductionsPage";

export default function SubmitAllDrafts({
  preview,
  busy,
  onRequest,
  onConfirm,
  onCancel,
}: {
  preview: DeductionsPageModel["actions"]["submitAll"]["preview"];
  busy: boolean;
  onRequest: () => void;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  if (preview) {
    return (
      <div
        role="dialog"
        aria-label="Confirm batch submission"
        style={{
          border: "1px solid #c9d6f2",
          background: "#eef4ff",
          borderRadius: 4,
          padding: 12,
          marginBottom: 12,
        }}
      >
        <p style={{ margin: "0 0 8px" }}>
          Submit all <strong>{preview.ids.length}</strong> submittable drafts for{" "}
          <strong>{preview.month}</strong>?
        </p>
        {preview.emptyCount > 0 && (
          <p style={{ margin: "0 0 8px", fontSize: 13, color: "#8a6d00" }}>
            {preview.emptyCount} draft(s) have no lines and will stay drafts.
          </p>
        )}
        <p style={{ margin: "0 0 8px", fontSize: 13, color: "#555" }}>
          Records that are already submitted, or that belong to a member you are conflicted against
          with an override, will be refused one by one and listed in the result.
        </p>
        <div style={{ display: "flex", gap: 8 }}>
          <button disabled={busy} onClick={onConfirm}>
            Submit {preview.ids.length} drafts
          </button>
          <button disabled={busy} onClick={onCancel}>
            Cancel
          </button>
        </div>
      </div>
    );
  }

  return (
    <button disabled={busy} onClick={onRequest}>
      Submit all drafts
    </button>
  );
}
