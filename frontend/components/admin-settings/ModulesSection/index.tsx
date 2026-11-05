import type { Settings } from "@/lib/api";
import { MODULE_FLAGS, MODULE_KEYS, MODULE_LABELS } from "@/lib/modules";
import type { ModuleFlag } from "@/lib/modules";

export default function ModulesSection({
  settings,
  setField,
}: {
  settings: Settings;
  setField: <K extends ModuleFlag>(key: K, value: Settings[K]) => void;
}) {
  return (
    <section>
      <h2>Modules</h2>
      <p style={{ color: "#555", fontSize: 14 }}>
        Disabling a module hides it from navigation and blocks its API for everyone. Staff
        accounts, roles, the audit log and this Settings page stay available so a disabled module
        can always be re-enabled. Save changes to apply them.
      </p>
      {MODULE_KEYS.map((module) => {
        const flag = MODULE_FLAGS[module];
        return (
          <label key={flag} style={{ display: "block", marginBottom: 8 }}>
            <input
              type="checkbox"
              checked={settings[flag]}
              onChange={(e) => setField(flag, e.target.checked)}
            />{" "}
            {MODULE_LABELS[module]} module enabled
          </label>
        );
      })}
    </section>
  );
}
