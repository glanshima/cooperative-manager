// A member's stored name is already the printed form "Last, First Other(s)"
// (composed by the backend from the registration fields). This helper turns
// it into the compact greeting form, where only the first given name is
// written out and every other name is reduced to an initial:
//   "Okafor, Adaeze Ngozi Chika" -> "Okafor, Adaeze N. C."
// Names without a comma (legacy/imported records) are split on whitespace
// with the final word as the family name. A single word is unchanged.
export function lastNameFirst(name: string | null | undefined): string | null {
  const trimmed = name?.trim();
  if (!trimmed) return null;

  const comma = trimmed.indexOf(",");
  if (comma >= 0) {
    const family = trimmed.slice(0, comma).trim();
    const given = trimmed
      .slice(comma + 1)
      .trim()
      .split(/\s+/)
      .filter(Boolean)
      .map((part, index) => (index === 0 ? part : `${part[0].toUpperCase()}.`));
    return given.length > 0 ? `${family}, ${given.join(" ")}` : family;
  }

  const parts = trimmed.split(/\s+/);
  if (parts.length === 1) return parts[0];

  const family = parts[parts.length - 1];
  const given = parts
    .slice(0, -1)
    .map((part, index) => (index === 0 ? part : `${part[0].toUpperCase()}.`));
  return `${family}, ${given.join(" ")}`;
}

// The registration form captures the name in parts. Editing an older record
// (or one created before the split) needs the same split done client-side so
// the three fields open prefilled rather than blank.
export function splitStoredName(name: string | null | undefined): {
  last_name: string;
  first_name: string;
  other_names: string;
} {
  const trimmed = name?.trim();
  if (!trimmed) return { last_name: "", first_name: "", other_names: "" };

  const comma = trimmed.indexOf(",");
  if (comma >= 0) {
    const given = trimmed
      .slice(comma + 1)
      .trim()
      .split(/\s+/)
      .filter(Boolean);
    return {
      last_name: trimmed.slice(0, comma).trim(),
      first_name: given[0] ?? "",
      other_names: given.slice(1).join(" "),
    };
  }

  const parts = trimmed.split(/\s+/);
  if (parts.length === 1) return { last_name: parts[0], first_name: "", other_names: "" };
  return {
    last_name: parts[parts.length - 1],
    first_name: parts[0],
    other_names: parts.slice(1, -1).join(" "),
  };
}

// The identity line above Log out: an admin is identified by the login they
// actually use; a member by their name. Members without a linked record (or
// without a stored name) fall back to the login.
// The stored name is printed in full here (abbreviating other names is a
// greeting-only choice); only a legacy given-name-first record is reordered.
export function userDisplayName(
  user: { username: string; role?: string; member_name?: string | null } | null | undefined
): string | null {
  if (!user) return null;
  if (user.role === "admin") return user.username;
  const stored = user.member_name?.trim();
  if (!stored) return user.username;
  return stored.includes(",") ? stored : lastNameFirst(stored);
}
