import type { InterestDeductionMode, LoanType } from "./api/loans";

// Mirrors app/loan_calc.compute_loan_terms. Previews are advisory: the
// server recomputes every figure with Decimal arithmetic at disbursement,
// so this only has to agree with it to the cent.
export interface LoanTermsPreview {
  interest: number;
  netDisbursed: number;
  totalRepayable: number;
  // Principal portion per month.
  installment: number;
  // Extra per month during the first spreadMonths instalments.
  interestInstallment: number;
  // The processing fee, owed separately -- shown, never part of the sums.
  fee: number;
}

function round2(value: number): number {
  return Math.round((value + Number.EPSILON) * 100) / 100;
}

export function computeLoanPreview(
  principal: number,
  interestRate: number,
  tenureMonths: number,
  mode: InterestDeductionMode = "at_source",
  spreadMonths?: number | null,
  fee = 0
): LoanTermsPreview {
  if (!principal || principal <= 0 || tenureMonths <= 0) {
    return {
      interest: 0,
      netDisbursed: 0,
      totalRepayable: 0,
      installment: 0,
      interestInstallment: 0,
      fee,
    };
  }

  const interest = round2(principal * interestRate);

  if (mode === "spread_first_months") {
    const months = spreadMonths && spreadMonths > 0 ? spreadMonths : 0;
    return {
      interest,
      netDisbursed: principal,
      totalRepayable: principal + interest,
      installment: round2(principal / tenureMonths),
      interestInstallment: months > 0 ? round2(interest / months) : 0,
      fee,
    };
  }

  if (mode === "spread_over_tenure") {
    return {
      interest,
      netDisbursed: principal,
      totalRepayable: principal + interest,
      installment: round2((principal + interest) / tenureMonths),
      interestInstallment: 0,
      fee,
    };
  }

  return {
    interest,
    netDisbursed: principal - interest,
    totalRepayable: principal,
    installment: round2(principal / tenureMonths),
    interestInstallment: 0,
    fee,
  };
}

// The type's cached terms win; a type with no mode of its own inherits the
// cooperative default.
export function resolveTypeInterestTerms(
  type: Pick<LoanType, "interest_mode" | "interest_spread_months"> | undefined,
  defaultMode: InterestDeductionMode = "at_source",
  defaultSpreadMonths: number | null = null
): { mode: InterestDeductionMode; spreadMonths: number | null } {
  return {
    mode: type?.interest_mode ?? defaultMode,
    spreadMonths: type?.interest_spread_months ?? defaultSpreadMonths,
  };
}

export const INTEREST_MODE_LABELS: Record<InterestDeductionMode, string> = {
  at_source: "Deducted at source",
  spread_over_tenure: "Spread over the tenure",
  spread_first_months: "Spread over the first months",
};
