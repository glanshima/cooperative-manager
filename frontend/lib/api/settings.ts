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
  cooperative_name: string;
  cooperative_short_name: string;
  cooperative_monogram: string;
  logo_url: string | null;
}

export async function getSettings(): Promise<Settings> {
  return apiFetch<Settings>("/api/settings");
}

export async function updateSettings(input: Partial<Settings>): Promise<Settings> {
  return apiFetch<Settings>("/api/settings", { method: "PUT", body: input });
}

export async function uploadLogo(contentType: string, imageBase64: string): Promise<Settings> {
  return apiFetch<Settings>("/api/settings/logo", {
    method: "POST",
    body: { content_type: contentType, image_base64: imageBase64 },
  });
}

export async function deleteLogo(): Promise<Settings> {
  return apiFetch<Settings>("/api/settings/logo", { method: "DELETE" });
}
