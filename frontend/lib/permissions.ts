// Client-side mirror of the backend's permission codes. These decide what
// the UI offers; the server still enforces every endpoint on its own.

export function hasPermission(permissions: readonly string[], code: string): boolean {
  return permissions.includes(code);
}

export function hasAnyPermission(permissions: readonly string[], codes: readonly string[]): boolean {
  return codes.some((code) => permissions.includes(code));
}

// Disbursements has no dedicated view permission: whoever can prepare,
// approve, submit or reconcile may also open the screen.
export const DISBURSEMENT_PERMISSIONS = [
  "disbursement.prepare",
  "disbursement.approve",
  "disbursement.submit",
  "disbursement.reconcile",
];

// Any of these opens the cooperative settings page; the page itself shows
// only the sections the account may actually change.
export const SETTINGS_PAGE_PERMISSIONS = [
  "admin.settings_manage",
  "branding.view",
  "branding.manage",
];
