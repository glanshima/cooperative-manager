import type { Settings } from "@/lib/api";
import type { SettingsPageModel } from "../hooks/useSettingsPage";

export default function LoanDefaultSettingsSection({
  settings,
  setField,
}: {
  settings: NonNullable<SettingsPageModel["settings"]>;
  setField: SettingsPageModel["setField"];
}) {
  return (
    <section>
      <h2>Loan defaults</h2>
      <label style={{ display: "block", marginBottom: 8 }}>
        Default charge (% of the missed instalment)
        <input
          type="number"
          step="0.01"
          min={0}
          max={100}
          value={settings.loan_default_charge_pct}
          onChange={(e) => setField("loan_default_charge_pct", e.target.value)}
          style={{ display: "block", padding: 8, marginTop: 4 }}
        />
        <span style={{ fontSize: 12, color: "var(--text-muted)" }}>
          Charged once per missed instalment, never compounded, and never taken from savings. 0
          means no charge.
        </span>
      </label>
      <label style={{ display: "block", marginBottom: 8 }}>
        When an unpaid instalment becomes a default
        <select
          value={settings.loan_default_grace_mode}
          onChange={(e) => {
            const mode = e.target.value as Settings["loan_default_grace_mode"];
            setField("loan_default_grace_mode", mode);
            if (mode !== "days") {
              setField("loan_default_grace_days", 0);
            }
          }}
          style={{ display: "block", padding: 8, marginTop: 4 }}
        >
          <option value="next_payroll">At the next payroll deduction</option>
          <option value="days">After a set number of days</option>
        </select>
        <span style={{ fontSize: 12, color: "var(--text-muted)" }}>
          At the next payroll deduction lets the member pay the whole instalment month before it
          counts. The day count runs from the end of that month.
        </span>
      </label>
      {settings.loan_default_grace_mode === "days" && (
        <label style={{ display: "block" }}>
          Days of grace
          <input
            type="number"
            min={0}
            max={365}
            value={settings.loan_default_grace_days}
            onChange={(e) => setField("loan_default_grace_days", parseInt(e.target.value) || 0)}
            style={{ display: "block", padding: 8, marginTop: 4 }}
          />
          <span style={{ fontSize: 12, color: "var(--text-muted)" }}>
            0 means the charge is raised as soon as the instalment month closes unpaid.
          </span>
        </label>
      )}
    </section>
  );
}
