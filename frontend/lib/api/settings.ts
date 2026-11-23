import { apiFetch } from "./client";
import type { InterestDeductionMode } from "./loans";

export type LoanRestrictionBehavior = "block" | "warn";

// NEXT_PAYROLL: a missed instalment only becomes a default when the next
// payroll deduction is processed. DAYS: a fixed window from the close of
// the instalment month, sized by loan_default_grace_days.
export type LoanDefaultGraceMode = "next_payroll" | "days";

export interface Settings {
  id: string;
  loan_restriction_behavior: LoanRestrictionBehavior;
  loan_form_fee: string;
  // Cooperative-wide default; a loan type or rate version may override it.
  loan_interest_mode: InterestDeductionMode;
  loan_interest_spread_months: number | null;
  // A member's agreed monthly contribution may not go below this. "0"
  // means the cooperative sets no floor.
  minimum_monthly_contribution: string;
  // What the add-member form starts at. "0" means leave it blank.
  default_monthly_contribution: string;
  // Charged once per missed instalment; never taken out of savings.
  loan_default_charge_pct: string;
  loan_default_grace_mode: LoanDefaultGraceMode;
  loan_default_grace_days: number;
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
