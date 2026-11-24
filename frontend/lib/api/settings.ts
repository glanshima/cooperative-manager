import { apiFetch } from "./client";
import type {
  DividendBasis,
  DividendPaymentPolicy,
  DividendPoolMode,
  DividendRounding,
} from "./dividends";
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
  // Month the cooperative's fiscal year opens in; the dividend run for a
  // year covers the twelve months that follow it.
  fiscal_year_start_month: number;
  dividend_basis: DividendBasis;
  dividend_pool_mode: DividendPoolMode;
  // The pool split must add up to 100.
  dividend_reserve_pct: string;
  dividend_honorarium_pct: string;
  dividend_payout_pct: string;
  dividend_declared_rate_pct: string | null;
  dividend_fixed_pool_amount: string | null;
  dividend_hybrid_savings_pct: string;
  dividend_min_membership_months: number;
  dividend_include_exited: boolean;
  dividend_rounding: DividendRounding;
  dividend_withholding_pct: string;
  dividend_payment_method: DividendPaymentPolicy;
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
