import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { getSettings } from "@/lib/api";
import type { Settings } from "@/lib/api";

import ModuleGate from ".";

vi.mock("@/lib/api", () => ({
  getSettings: vi.fn(),
}));

const getSettingsMock = vi.mocked(getSettings);

const settings: Settings = {
  id: "settings-1",
  loan_restriction_behavior: "block",
  loan_form_fee: "50.00",
  loan_interest_mode: "at_source",
  loan_interest_spread_months: null,
  minimum_monthly_contribution: "0.00",
  default_monthly_contribution: "0.00",
  loan_default_charge_pct: "0.00",
  loan_default_grace_mode: "next_payroll",
  loan_default_grace_days: 0,
  members_module_enabled: true,
  loans_module_enabled: true,
  deductions_module_enabled: true,
  cashbook_module_enabled: true,
  dividends_module_enabled: true,
  fiscal_year_start_month: 1,
  dividend_basis: "net_savings_closing",
  dividend_pool_mode: "net_income_share",
  dividend_reserve_pct: "4.70",
  dividend_honorarium_pct: "3.00",
  dividend_payout_pct: "92.30",
  dividend_declared_rate_pct: null,
  dividend_fixed_pool_amount: null,
  dividend_hybrid_savings_pct: "50.00",
  dividend_min_membership_months: 0,
  dividend_include_exited: false,
  dividend_rounding: "two_dp",
  dividend_withholding_pct: "0.00",
  dividend_payment_method: "bank",
  cooperative_name: "MACT Cooperative",
  cooperative_short_name: "MACT",
  cooperative_monogram: "M",
  logo_url: null,
};

describe("ModuleGate", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    getSettingsMock.mockResolvedValue(settings);
  });

  it("renders children when the module is enabled", async () => {
    render(
      <ModuleGate module="loans">
        <p>Loan content</p>
      </ModuleGate>
    );

    expect(await screen.findByText("Loan content")).toBeInTheDocument();
    expect(screen.queryByText("Loans module disabled")).not.toBeInTheDocument();
  });

  it("renders the disabled state when the module is off", async () => {
    getSettingsMock.mockResolvedValue({ ...settings, loans_module_enabled: false });

    render(
      <ModuleGate module="loans">
        <p>Loan content</p>
      </ModuleGate>
    );

    expect(await screen.findByText("Loans module disabled")).toBeInTheDocument();
    expect(screen.queryByText("Loan content")).not.toBeInTheDocument();
  });

  it("surfaces settings fetch failures instead of rendering the module", async () => {
    getSettingsMock.mockRejectedValue(new Error("network down"));

    render(
      <ModuleGate module="members">
        <p>Member content</p>
      </ModuleGate>
    );

    expect(
      await screen.findByText("Unable to check module availability: network down")
    ).toBeInTheDocument();
    expect(screen.queryByText("Member content")).not.toBeInTheDocument();
  });
});
