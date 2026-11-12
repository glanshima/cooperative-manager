// How many rows a page holds, remembered per officer.
//
// Stored in the browser rather than on the account: it is a display
// preference, it belongs to whoever is sitting at the keyboard, and the
// cooperative has no screen where an admin sets another user's layout.
const STORAGE_KEY = "cooperative.pageSize";

export const PAGE_SIZE_OPTIONS = [20, 50, 100];

/** The officer's chosen size, or null when they have never picked one and
 *  each list should use the default that suits it. */
export function readStoredPageSize(): number | null {
  if (typeof window === "undefined") return null;
  const stored = Number(window.localStorage.getItem(STORAGE_KEY));
  return PAGE_SIZE_OPTIONS.includes(stored) ? stored : null;
}

export function storePageSize(value: number): void {
  window.localStorage.setItem(STORAGE_KEY, String(value));
}
