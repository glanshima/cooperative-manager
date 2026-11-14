import { describe, expect, it } from "vitest";

import { computeDisbursePreview } from "./useLoansPage";

const TYPE = { interest_rate: "0.15", flat_charge: "0.00", tenure_months: 12 };

describe("computeDisbursePreview", () => {
  it("deducts interest at source instead of adding it to the repayable total", () => {
    // The backend's total_repayable is principal + flat_charge; interest
    // lowers what the member receives. A preview that added interest made
    // the total (and so the instalment) too high by interest/tenure.
    const preview = computeDisbursePreview(100_000, TYPE);

    expect(preview.interest).toBeCloseTo(15_000, 2);
    expect(preview.netDisbursed).toBeCloseTo(85_000, 2);
    expect(preview.total).toBeCloseTo(100_000, 2);
    expect(preview.installment).toBeCloseTo(100_000 / 12, 6);
  });

  it("adds a flat charge, and only a flat charge, to the repayable total", () => {
    const preview = computeDisbursePreview(100_000, {
      ...TYPE,
      flat_charge: "1000.00",
    });

    expect(preview.total).toBeCloseTo(101_000, 2);
    expect(preview.installment).toBeCloseTo(101_000 / 12, 6);
  });

  it("is all zeroes until a loan type is chosen", () => {
    expect(computeDisbursePreview(100_000, undefined)).toEqual({
      interest: 0,
      netDisbursed: 0,
      flatCharge: 0,
      total: 0,
      installment: 0,
    });
  });
});
