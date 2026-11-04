export default function MemberSearch({
  value,
  onChange,
  onSearch,
  onClear,
}: {
  value: string;
  onChange: (value: string) => void;
  onSearch: () => void;
  onClear: () => void;
}) {
  return (
    <section style={{ marginBottom: 12 }}>
      <span style={{ position: "relative", display: "inline-block" }}>
        <input
          placeholder="Search by member number/PSN, name, or phone"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && onSearch()}
          style={{ padding: 8, paddingRight: value ? 28 : 8, width: 320, marginRight: 8 }}
        />
        {value && (
          <button
            onClick={onClear}
            aria-label="Clear search"
            style={{
              position: "absolute",
              right: 36,
              top: "50%",
              transform: "translateY(-50%)",
              border: "none",
              background: "transparent",
              cursor: "pointer",
              fontSize: 16,
              lineHeight: 1,
              padding: 4,
            }}
          >
            ×
          </button>
        )}
      </span>
      <button onClick={onSearch}>Search</button>
    </section>
  );
}
