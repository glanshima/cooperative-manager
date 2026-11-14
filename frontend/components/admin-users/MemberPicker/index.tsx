import type { CSSProperties } from "react";
import type { Member } from "@/lib/api";
import { describeMember } from "../utils";

export default function MemberPicker({
  query,
  results,
  onQueryChange,
  onSearch,
  onSelect,
  style,
}: {
  query: string;
  results: Member[];
  onQueryChange: (value: string) => void;
  onSearch: () => void;
  onSelect: (member: Member) => void;
  style?: CSSProperties;
}) {
  return (
    <>
      <span className="toolbar" style={style}>
        <span className="search-field">
          <input
            placeholder="Search member by PSN, name, or phone"
            value={query}
            onChange={(e) => onQueryChange(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && (e.preventDefault(), onSearch())}
            style={{ padding: 6 }}
          />
        </span>
        <button type="button" onClick={onSearch}>
          Search
        </button>
      </span>
      {results.length > 0 && (
        <ul style={{ marginTop: 8, paddingLeft: 16 }}>
          {results.map((m) => (
            <li key={m.id}>
              {describeMember(m)}{" "}
              <button type="button" onClick={() => onSelect(m)}>
                Select
              </button>
            </li>
          ))}
        </ul>
      )}
    </>
  );
}
