// Member names are stored as one free-text field, so the formal
// "Last, First" form is derived from the final word. Only the first given
// name is written out; middle names are reduced to initials. Names that
// already contain a comma are treated as written, and a single word is
// unchanged.
export function lastNameFirst(name: string | null | undefined): string | null {
  const trimmed = name?.trim();
  if (!trimmed) return null;
  if (trimmed.includes(",")) return trimmed;

  const parts = trimmed.split(/\s+/);
  if (parts.length === 1) return parts[0];

  const lastName = parts[parts.length - 1];
  const givenNames = parts
    .slice(0, -1)
    .map((part, index) => (index === 0 ? part : `${part[0].toUpperCase()}.`));
  return `${lastName}, ${givenNames.join(" ")}`;
}

// The name to show above log out on any screen: the linked member's name when
// there is one, otherwise the login an admin actually uses.
export function userDisplayName(user: { username: string; member_name?: string | null } | null | undefined): string | null {
  if (!user) return null;
  return lastNameFirst(user.member_name) ?? user.username;
}
