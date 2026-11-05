import type { Settings } from "@/lib/api";

export type ModuleKey = "members" | "loans" | "deductions" | "cashbook" | "dividends";

export type ModuleFlag =
  | "members_module_enabled"
  | "loans_module_enabled"
  | "deductions_module_enabled"
  | "cashbook_module_enabled"
  | "dividends_module_enabled";

export const MODULE_KEYS: ModuleKey[] = ["members", "loans", "deductions", "cashbook", "dividends"];

export const MODULE_FLAGS: Record<ModuleKey, ModuleFlag> = {
  members: "members_module_enabled",
  loans: "loans_module_enabled",
  deductions: "deductions_module_enabled",
  cashbook: "cashbook_module_enabled",
  dividends: "dividends_module_enabled",
};

export const MODULE_LABELS: Record<ModuleKey, string> = {
  members: "Members",
  loans: "Loans",
  deductions: "Deductions",
  cashbook: "Cashbook",
  dividends: "Dividends",
};

export function isModuleEnabled(settings: Settings, module: ModuleKey): boolean {
  return Boolean(settings[MODULE_FLAGS[module]]);
}
