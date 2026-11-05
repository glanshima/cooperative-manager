import { apiFetch } from "./client";

export type LoanRestrictionBehavior = "block" | "warn";

export interface Settings {
  id: string;
  loan_restriction_behavior: LoanRestrictionBehavior;
  loan_form_fee: string;
  members_module_enabled: boolean;
  loans_module_enabled: boolean;
  deductions_module_enabled: boolean;
  cashbook_module_enabled: boolean;
  dividends_module_enabled: boolean;
}

export async function getSettings(): Promise<Settings> {
  return apiFetch<Settings>("/api/settings");
}

export async function updateSettings(input: Partial<Settings>): Promise<Settings> {
  return apiFetch<Settings>("/api/settings", { method: "PUT", body: input });
}
