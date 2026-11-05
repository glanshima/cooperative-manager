import type { AuditPageModel } from "../hooks/useAuditPage";

export default function AuditFilters({ filters }: { filters: AuditPageModel["filters"] }) {
  return (
    <form
      onSubmit={filters.submit}
      style={{ display: "flex", gap: 8, alignItems: "flex-end", marginBottom: 16 }}
    >
      <label>
        Entity type
        <input
          value={filters.entityType}
          onChange={(e) => filters.setEntityType(e.target.value)}
          placeholder="e.g. loan_application"
          style={{ display: "block", padding: 8 }}
        />
      </label>
      <label>
        Event type
        <input
          value={filters.eventType}
          onChange={(e) => filters.setEventType(e.target.value)}
          placeholder="e.g. auth.login_failed"
          style={{ display: "block", padding: 8 }}
        />
      </label>
      <button type="submit">Filter</button>
    </form>
  );
}
