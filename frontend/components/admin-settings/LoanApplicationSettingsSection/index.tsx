import { INTEREST_MODE_LABELS } from "@/lib/loanMath";
import type { Settings } from "@/lib/api";
import type { SettingsPageModel } from "../hooks/useSettingsPage";

export default function LoanApplicationSettingsSection({
  settings,
  setField,
}: {
  settings: NonNullable<SettingsPageModel["settings"]>;
  setField: SettingsPageModel["setField"];
}) {
  return (
    <section>
      <h2>Loan applications</h2>
      <label style={{ display: "block", marginBottom: 8 }}>
        Universal loan/application fee
        <input
          type="number"
          min="0"
          step="0.01"
          value={settings.loan_form_fee}
          onChange={(e) => setField("loan_form_fee", e.target.value)}
          style={{ display: "block", padding: 8, marginTop: 4 }}
        />
        <span style={{ display: "block", marginTop: 4, fontSize: 12, color: "var(--text-muted)" }}>
          One fee for every loan type, paid separately from the loan. Each new application or
          direct loan keeps a snapshot of this amount.
        </span>
      </label>
      <label style={{ display: "block", marginBottom: 8 }}>
        Interest deduction (applies to loan types without their own setting)
        <select
          value={settings.loan_interest_mode}
          onChange={(e) => {
            const mode = e.target.value as Settings["loan_interest_mode"];
            setField("loan_interest_mode", mode);
            if (mode !== "spread_first_months") {
              setField("loan_interest_spread_months", null);
            }
          }}
          style={{ display: "block", padding: 8, marginTop: 4 }}
        >
          {Object.entries(INTEREST_MODE_LABELS).map(([mode, label]) => (
            <option key={mode} value={mode}>
              {label}
            </option>
          ))}
        </select>
      </label>
      {settings.loan_interest_mode === "spread_first_months" && (
        <label style={{ display: "block", marginBottom: 8 }}>
          Months the interest is spread over
          <input
            required
            type="number"
            min={1}
            value={settings.loan_interest_spread_months ?? ""}
            onChange={(e) =>
              setField("loan_interest_spread_months", parseInt(e.target.value) || null)
            }
            style={{ display: "block", padding: 8, marginTop: 4 }}
          />
        </label>
      )}
      <label style={{ display: "block" }}>
        When a restricted member applies:
        <select
          value={settings.loan_restriction_behavior}
          onChange={(e) =>
            setField(
              "loan_restriction_behavior",
              e.target.value as "block" | "warn"
            )
          }
          style={{ display: "block", padding: 8, marginTop: 4 }}
        >
          <option value="warn">Warn admin, allow application</option>
          <option value="block">Block the application entirely</option>
        </select>
      </label>
    </section>
  );
}
