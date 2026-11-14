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
    <section className="toolbar" style={{ marginBottom: 12 }}>
      <span className="search-field">
        <input
          placeholder="Search by member number/PSN, name, or phone"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && onSearch()}
          style={{ padding: 8, paddingRight: value ? 32 : 8 }}
        />
        {value && (
          <button
            className="search-field__clear"
            onClick={onClear}
            aria-label="Clear search"
          >
            ×
          </button>
        )}
      </span>
      <button onClick={onSearch}>Search</button>
    </section>
  );
}
