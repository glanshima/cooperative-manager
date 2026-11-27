import { describe, expect, it } from "vitest";

import { computeDisbursePreview } from "./useLoansPage";

const TYPE = { interest_rate: "0.15", tenure_months: 12 };

describe("computeDisbursePreview", () => {
  it("deducts interest at source instead of adding it to the repayable total", () => {
    // Interest lowers what the member receives; the member still repays the
    // full principal.
    const preview = computeDisbursePreview(100_000, TYPE);

    expect(preview.interest).toBeCloseTo(15_000, 2);
    expect(preview.netDisbursed).toBeCloseTo(85_000, 2);
    expect(preview.total).toBeCloseTo(100_000, 2);
    expect(preview.installment).toBeCloseTo(8333.33, 2);
    expect(preview.mode).toBe("at_source");
  });

  it("uses the universal loan fee without adding it to the loan figures", () => {
    const preview = computeDisbursePreview(100_000, TYPE, undefined, undefined, 1000);

    expect(preview.fee).toBeCloseTo(1000, 2);
    expect(preview.total).toBeCloseTo(100_000, 2);
    expect(preview.installment).toBeCloseTo(8333.33, 2);
    expect(preview.netDisbursed).toBeCloseTo(85_000, 2);
  });

  it("spreads interest over the whole tenure when configured", () => {
    const preview = computeDisbursePreview(100_000, {
      ...TYPE,
      interest_mode: "spread_over_tenure",
    });

    expect(preview.netDisbursed).toBeCloseTo(100_000, 2);
    expect(preview.total).toBeCloseTo(115_000, 2);
    expect(preview.installment).toBeCloseTo(9583.33, 2);
  });

  it("adds the interest portion on top for the first months only", () => {
    const preview = computeDisbursePreview(100_000, {
      ...TYPE,
      tenure_months: 6,
      interest_mode: "spread_first_months",
      interest_spread_months: 3,
    });

    expect(preview.netDisbursed).toBeCloseTo(100_000, 2);
    expect(preview.total).toBeCloseTo(115_000, 2);
    expect(preview.installment).toBeCloseTo(16666.67, 2);
    expect(preview.interestInstallment).toBeCloseTo(15_000 / 3, 6);
    expect(preview.spreadMonths).toBe(3);
  });

  it("falls back to the cooperative default when the type has no mode", () => {
    const preview = computeDisbursePreview(
      100_000,
      TYPE,
      "spread_over_tenure",
      null
    );

    expect(preview.mode).toBe("spread_over_tenure");
    expect(preview.total).toBeCloseTo(115_000, 2);
  });

  it("is all zeroes until a loan type is chosen", () => {
    expect(computeDisbursePreview(100_000, undefined)).toEqual({
      interest: 0,
      netDisbursed: 0,
      fee: 0,
      total: 0,
      installment: 0,
      interestInstallment: 0,
      mode: "at_source",
      spreadMonths: null,
    });
  });
});
