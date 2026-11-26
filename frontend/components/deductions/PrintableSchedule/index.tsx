"use client";

import { useEffect } from "react";

import { useBranding } from "@/components/branding/BrandingProvider";
import Table from "@/components/ui/Table";
import type { PayrollDeductionSchedule } from "@/lib/api";

import { monthLabel } from "@/lib/month";

import { formatMoney } from "../labels";

const cellStyle = { padding: "6px 8px", borderBottom: "1px solid #ccc", verticalAlign: "top" };

export default function PrintableSchedule({
  schedule,
  onClose,
}: {
  schedule: PayrollDeductionSchedule | null;
  onClose: () => void;
}) {
  const { branding } = useBranding();

  useEffect(() => {
    const timer = setTimeout(() => window.print(), 100);
    return () => clearTimeout(timer);
  }, []);

  if (!schedule) {
    return (
      <main className="page">
        <p>The schedule has not loaded yet.</p>
        <button onClick={onClose}>Back</button>
      </main>
    );
  }

  // The printed schedule is what payroll acts on, so records payroll will not
  // deduct are left off; they remain visible (with reasons) on screen.
  const rows = schedule.records.filter((record) => record.status !== "not_deducted");

  return (
    <main className="page page--1100">
      <style>{`@media print {
        .no-print { display: none !important; }
        body { margin: 12mm; }
        body > footer { display: none !important; }
      }`}</style>

      <div className="toolbar no-print" style={{ marginBottom: 16 }}>
        <button onClick={() => window.print()}>Print</button>
        <button onClick={onClose}>Back to deductions</button>
      </div>

      <header style={{ marginBottom: 16 }}>
        {branding.logo_url && (
          <img
            src={branding.logo_url}
            alt=""
            style={{ display: "block", height: 48, width: "auto", marginBottom: 8 }}
          />
        )}
        <h1 style={{ marginBottom: 4 }}>{branding.cooperative_name}</h1>
        <h2 style={{ marginTop: 0, fontSize: 18 }}>Payroll Deduction Schedule</h2>
        <p style={{ margin: "0 0 4px", fontWeight: 500 }}>{monthLabel(schedule.month)}</p>
        <p style={{ color: "#555", margin: 0 }}>
          Prepared on {new Date().toLocaleDateString()}.
        </p>
      </header>

      <Table>
        <thead>
          <tr style={{ textAlign: "left", borderBottom: "2px solid #333" }}>
            <th style={cellStyle}>PSN</th>
            <th style={cellStyle}>Member</th>
            <th style={cellStyle}>Savings</th>
            <th style={cellStyle}>Loans</th>
            <th style={cellStyle}>Arrears</th>
            <th style={cellStyle}>Other</th>
            <th style={cellStyle}>Total</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((record) => (
            <tr key={record.id}>
              <td style={cellStyle}>{record.member_psn?.replace("MCT-", "") ?? ""}</td>
              <td style={cellStyle}>{record.member_name ?? "Unknown member"}</td>
              <td style={cellStyle}>{formatMoney(record.contribution_total)}</td>
              <td style={cellStyle}>{formatMoney(record.loan_total)}</td>
              <td style={cellStyle}>{formatMoney(record.arrears_total)}</td>
              <td style={cellStyle}>{formatMoney(record.other_total)}</td>
              <td style={cellStyle}>
                <strong>{formatMoney(record.grand_total)}</strong>
              </td>
            </tr>
          ))}
        </tbody>
        <tfoot>
          <tr style={{ borderTop: "2px solid #333", fontWeight: 700 }}>
            <td style={cellStyle} colSpan={2}>
              Totals
            </td>
            <td style={cellStyle}>{formatMoney(schedule.totals.contribution_total)}</td>
            <td style={cellStyle}>{formatMoney(schedule.totals.loan_total)}</td>
            <td style={cellStyle}>{formatMoney(schedule.totals.arrears_total)}</td>
            <td style={cellStyle}>{formatMoney(schedule.totals.other_total)}</td>
            <td style={cellStyle}>{formatMoney(schedule.totals.grand_total)}</td>
          </tr>
        </tfoot>
      </Table>

      <footer style={{ marginTop: 24, textAlign: "center", fontSize: 12, color: "#555" }}>
        © {branding.cooperative_name} {schedule.month.slice(0, 4)}
      </footer>
    </main>
  );
}
