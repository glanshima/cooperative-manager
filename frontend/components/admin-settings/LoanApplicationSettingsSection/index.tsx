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
        Loan form fee
        <input
          type="number"
          step="0.01"
          value={settings.loan_form_fee}
          onChange={(e) => setField("loan_form_fee", e.target.value)}
          style={{ display: "block", padding: 8, marginTop: 4 }}
        />
      </label>
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
