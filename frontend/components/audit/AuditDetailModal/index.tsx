import Modal from "@/components/ui/Modal";
import type { AuditPageModel } from "../hooks/useAuditPage";

export default function AuditDetailModal({ detail }: { detail: AuditPageModel["detail"] }) {
  const selected = detail.event;
  if (!selected) return null;

  return (
    <Modal
      title={selected.event_type}
      onClose={detail.close}
      closeLabel="Close audit detail"
      maxWidth={600}
    >
      <p>
        <strong>Actor:</strong> {selected.actor_username || "(unknown)"}{" "}
        {selected.actor_office_name && `(${selected.actor_office_name})`}
      </p>
      <p>
        <strong>Entity:</strong> {selected.entity_type} {selected.entity_id}
      </p>
      <p>
        <strong>Reason:</strong> {selected.reason || "-"}
      </p>
      <p>
        <strong>IP:</strong> {selected.ip_address || "-"}
      </p>
      {selected.previous_values && (
        <>
          <strong>Previous values</strong>
          <pre style={{ background: "#f5f5f5", padding: 8, overflow: "auto" }}>
            {JSON.stringify(selected.previous_values, null, 2)}
          </pre>
        </>
      )}
      {selected.new_values && (
        <>
          <strong>New values</strong>
          <pre style={{ background: "#f5f5f5", padding: 8, overflow: "auto" }}>
            {JSON.stringify(selected.new_values, null, 2)}
          </pre>
        </>
      )}
    </Modal>
  );
}
