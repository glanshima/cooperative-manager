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
  members_module_enabled: true,
  loans_module_enabled: true,
  deductions_module_enabled: true,
  cashbook_module_enabled: true,
  dividends_module_enabled: true,
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
