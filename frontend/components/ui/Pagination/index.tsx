import { PAGE_SIZE_OPTIONS } from "@/lib/pageSize";

export default function Pagination({
  skip,
  limit,
  total,
  onChange,
  onPageSizeChange,
}: {
  skip: number;
  limit: number;
  total: number;
  onChange: (newSkip: number) => void;
  // Only lists where the officer picks the size pass this; the rest keep the
  // plain Previous / Next control and their fixed page size.
  onPageSizeChange?: (newLimit: number) => void;
}) {
  return (
    <div style={{ marginTop: 12, display: "flex", gap: 8, alignItems: "center" }}>
      <button disabled={skip === 0} onClick={() => onChange(skip - limit)}>
        Previous
      </button>
      <span>
        Page {Math.floor(skip / limit) + 1} of {Math.max(1, Math.ceil(total / limit))}
      </span>
      <button disabled={skip + limit >= total} onClick={() => onChange(skip + limit)}>
        Next
      </button>
      {onPageSizeChange && (
        <label style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 6, fontSize: 13 }}>
          Rows per page
          <select
            value={limit}
            onChange={(e) => onPageSizeChange(Number(e.target.value))}
            aria-label="Rows per page"
          >
            {PAGE_SIZE_OPTIONS.map((option) => (
              <option key={option} value={option}>
                {option}
              </option>
            ))}
          </select>
        </label>
      )}
    </div>
  );
}
