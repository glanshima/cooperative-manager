import type { MemberStatus } from "@/lib/api";

export default function MemberFilters({
  bank,
  department,
  status,
  options,
  hasActive,
  onBankChange,
  onDepartmentChange,
  onStatusChange,
  onClear,
}: {
  bank: string;
  department: string;
  status: MemberStatus | "";
  options: { banks: string[]; departments: string[] };
  hasActive: boolean;
  onBankChange: (value: string) => void;
  onDepartmentChange: (value: string) => void;
  onStatusChange: (value: MemberStatus | "") => void;
  onClear: () => void;
}) {
  return (
    <section style={{ marginBottom: 12, display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap" }}>
      <label>
        Bank{" "}
        <select value={bank} onChange={(e) => onBankChange(e.target.value)}>
          <option value="">All Banks</option>
          {options.banks.map((b) => (
            <option key={b} value={b}>
              {b}
            </option>
          ))}
        </select>
      </label>
      <label>
        Department{" "}
        <select value={department} onChange={(e) => onDepartmentChange(e.target.value)}>
          <option value="">All Departments</option>
          {options.departments.map((d) => (
            <option key={d} value={d}>
              {d}
            </option>
          ))}
        </select>
      </label>
      <label>
        Status{" "}
        <select value={status} onChange={(e) => onStatusChange(e.target.value as MemberStatus | "")}>
          <option value="">All Statuses</option>
          <option value="financial">Financial</option>
          <option value="non_financial">Non-financial</option>
        </select>
      </label>
      {hasActive && <button onClick={onClear}>Clear Filters</button>}
    </section>
  );
}
