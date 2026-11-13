import { render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { PayrollDeductionSchedule } from "@/lib/api";

import PrintableSchedule from ".";

const schedule: PayrollDeductionSchedule = {
  month: "2026-11-01",
  records: [
    {
      id: "deduction-1",
      member_id: "member-1",
      member_name: "Ada Obi",
      member_psn: "0001",
      deduction_month: "2026-11-01",
      payroll_reference: "PAY-2026-11",
      note: null,
      status: "submitted",
      contribution_total: "2000.00",
      loan_total: "500.00",
      arrears_total: "200.00",
      other_total: "100.00",
      grand_total: "2800.00",
      submitted_at: "2026-11-02T00:00:00Z",
      confirmed_at: null,
      not_deducted_at: null,
      not_deducted_reason: null,
      returned_at: null,
      return_reason: null,
      voided_at: null,
      void_reason: null,
      created_at: "2026-11-01T00:00:00Z",
      updated_at: "2026-11-01T00:00:00Z",
      lines: [
        {
          id: "line-1",
          category: "loan_repayment",
          loan_id: "loan-1",
          label: null,
          amount: "500.00",
          loan_type_name: "Capital Loan",
        },
        {
          id: "line-2",
          category: "loan_arrears",
          loan_id: "loan-1",
          label: null,
          amount: "200.00",
          loan_type_name: "Capital Loan",
        },
      ],
    },
  ],
  totals: {
    contribution_total: "2000.00",
    loan_total: "500.00",
    arrears_total: "200.00",
    other_total: "100.00",
    grand_total: "2800.00",
  },
};

describe("PrintableSchedule", () => {
  beforeEach(() => {
    vi.stubGlobal("print", vi.fn());
  });

  it("renders the cooperative heading, month, member and totals", () => {
    render(<PrintableSchedule schedule={schedule} onClose={vi.fn()} />);

    expect(screen.getByRole("heading", { name: "MACT Cooperative" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /payroll deduction schedule/i })).toBeInTheDocument();
    expect(screen.getByText("November 2026")).toBeInTheDocument();
    expect(screen.getByText("Arrears")).toBeInTheDocument();

    const memberRow = screen.getByText("Ada Obi").closest("tr");
    expect(memberRow).not.toBeNull();
    expect(within(memberRow!).getByText("2,800.00")).toBeInTheDocument();
    expect(within(memberRow!).getByText("500.00")).toBeInTheDocument();
    expect(within(memberRow!).getByText("200.00")).toBeInTheDocument();

    const totalsRow = screen.getByText("Totals").closest("tr");
    expect(totalsRow).not.toBeNull();
    expect(totalsRow).toHaveTextContent("2,000.00");
    expect(totalsRow).toHaveTextContent("2,800.00");

    expect(screen.queryByText("Breakdown")).not.toBeInTheDocument();
    expect(screen.queryByText("Status")).not.toBeInTheDocument();
    expect(screen.getByText("© MACT Cooperative 2026")).toBeInTheDocument();
  });

  it("displays PSN as first column without MCT prefix", () => {
    render(<PrintableSchedule schedule={schedule} onClose={vi.fn()} />);

    // Verify PSN is first column in header
    const headers = screen.getAllByRole("columnheader");
    expect(headers[0]).toHaveTextContent("PSN");
    expect(headers[1]).toHaveTextContent("Member");

    // Verify PSN is first column in data row and doesn't have MCT prefix
    const memberRow = screen.getByText("Ada Obi").closest("tr");
    expect(memberRow).not.toBeNull();
    
    const cells = within(memberRow!).getAllByRole("cell");
    expect(cells[0]).toHaveTextContent("0001"); // PSN without MCT prefix
    expect(cells[1]).toHaveTextContent("Ada Obi"); // Member name
  });

  it("omits not-deducted records from the printed schedule", () => {
    const notDeducted: PayrollDeductionSchedule = {
      ...schedule,
      records: [
        {
          ...schedule.records[0],
          id: "deduction-2",
          member_id: "member-2",
          member_name: "Ngozi Adeyemi",
          member_psn: "0002",
          status: "not_deducted",
          not_deducted_reason: "Payroll omitted",
        },
      ],
    };

    render(<PrintableSchedule schedule={notDeducted} onClose={vi.fn()} />);

    expect(screen.queryByText("Ngozi Adeyemi")).not.toBeInTheDocument();
  });
});
