import type { DisbursementsPageModel } from "../hooks/useDisbursementsPage";

export default function DisbursementFilters({
  filters,
}: {
  filters: DisbursementsPageModel["filters"];
}) {
  return (
    <section style={{ marginBottom: 16, display: "flex", gap: 8, flexWrap: "wrap" }}>
      <select
        value={filters.loanTypeId}
        onChange={(e) => filters.setLoanTypeId(e.target.value)}
      >
        <option value="">All loan types</option>
        {filters.types.map((t) => (
          <option key={t.id} value={t.id}>
            {t.name}
          </option>
        ))}
      </select>
      <label>
        Approved from:{" "}
        <input
          type="date"
          value={filters.from}
          onChange={(e) => filters.setFrom(e.target.value)}
        />
      </label>
      <label>
        to:{" "}
        <input
          type="date"
          value={filters.to}
          onChange={(e) => filters.setTo(e.target.value)}
        />
      </label>
    </section>
  );
}
