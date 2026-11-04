export default function Pagination({
  skip,
  limit,
  total,
  onChange,
}: {
  skip: number;
  limit: number;
  total: number;
  onChange: (newSkip: number) => void;
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
    </div>
  );
}
