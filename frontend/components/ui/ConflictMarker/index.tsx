import type { CSSProperties } from "react";

const AMBER = "#b45309";

const chipStyle: CSSProperties = {
  color: AMBER,
  fontWeight: 600,
  fontSize: 13,
  whiteSpace: "nowrap",
};

const noticeStyle: CSSProperties = {
  ...chipStyle,
  fontWeight: 400,
  background: "#fef3c7",
  border: `1px solid ${AMBER}`,
  borderRadius: 4,
  padding: "8px 12px",
  margin: "12px 0",
};

/** Inline label for a table cell: the record is visible but read-only. */
export function ConflictMarker({ reason }: { reason?: string }) {
  return (
    <span style={chipStyle} title={reason ?? DEFAULT_REASON}>
      ⚠ conflict
    </span>
  );
}

/** Block explanation for a detail panel, where a bare chip isn't enough. */
export function ConflictNotice({ entity = "record" }: { entity?: string }) {
  return (
    <p role="note" style={noticeStyle}>
      {DEFAULT_REASON} You can view this {entity}, but the actions are disabled — another
      eligible officer has to carry them out.
    </p>
  );
}

const DEFAULT_REASON =
  "This record belongs to a member you are linked to by a conflict-of-interest relationship.";
