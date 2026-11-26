import type { Settings } from "@/lib/api";
import type { SettingsPageModel } from "../hooks/useSettingsPage";

export default function ContributionSettingsSection({
  settings,
  setField,
}: {
  settings: NonNullable<SettingsPageModel["settings"]>;
  setField: SettingsPageModel["setField"];
}) {
  const minimum = Number(settings.minimum_monthly_contribution);
  const formDefault = Number(settings.default_monthly_contribution);
  const belowFloor = minimum > 0 && formDefault > 0 && formDefault < minimum;

  return (
    <section>
      <h2>Savings</h2>
      <label style={{ display: "block", marginBottom: 8 }}>
        Minimum monthly savings
        <input
          type="number"
          step="0.01"
          min={0}
          value={settings.minimum_monthly_contribution}
          onChange={(e) => setField("minimum_monthly_contribution", e.target.value)}
          style={{ display: "block", padding: 8, marginTop: 4 }}
        />
        <span style={{ fontSize: 12, color: "var(--text-muted)" }}>
          A member&apos;s agreed savings cannot be lower than this. 0 means no minimum.
        </span>
      </label>
      <label style={{ display: "block" }}>
        Default on the add-member form
        <input
          type="number"
          step="0.01"
          min={0}
          value={settings.default_monthly_contribution}
          onChange={(e) => setField("default_monthly_contribution", e.target.value)}
          style={{ display: "block", padding: 8, marginTop: 4 }}
        />
        <span style={{ fontSize: 12, color: "var(--text-muted)" }}>
          0 leaves the amount blank. It is a starting figure only &mdash; an officer can change it
          before saving.
        </span>
      </label>
      {belowFloor && (
        <p role="alert" style={{ color: "var(--danger)", fontSize: 13, marginTop: 8 }}>
          The default is below the minimum, so this cannot be saved.
        </p>
      )}
    </section>
  );
}
