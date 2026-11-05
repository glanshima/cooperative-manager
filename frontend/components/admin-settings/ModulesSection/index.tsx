import type { SettingsPageModel } from "../hooks/useSettingsPage";

const MODULE_TOGGLES = [
  ["members_module_enabled", "Members"],
  ["loans_module_enabled", "Loans"],
  ["deductions_module_enabled", "Deductions"],
  ["cashbook_module_enabled", "Cashbook"],
  ["dividends_module_enabled", "Dividends"],
] as const;

export default function ModulesSection({
  settings,
  setField,
}: {
  settings: NonNullable<SettingsPageModel["settings"]>;
  setField: SettingsPageModel["setField"];
}) {
  return (
    <section>
      <h2>Modules</h2>
      {MODULE_TOGGLES.map(([key, label]) => (
        <label key={key} style={{ display: "block", marginBottom: 8 }}>
          <input
            type="checkbox"
            checked={settings[key]}
            onChange={(e) => setField(key, e.target.checked)}
          />{" "}
          {label} module enabled
        </label>
      ))}
    </section>
  );
}
