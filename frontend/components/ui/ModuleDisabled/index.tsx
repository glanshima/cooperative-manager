import { MODULE_LABELS } from "@/lib/modules";
import type { ModuleKey } from "@/lib/modules";

export default function ModuleDisabled({ module }: { module: ModuleKey }) {
  const label = MODULE_LABELS[module];
  return (
    <main style={{ padding: 32, maxWidth: 640 }}>
      <h1>{label} module disabled</h1>
      <p>The {label} module has been disabled by an administrator.</p>
      <p>If you need it, ask an administrator to re-enable it in Settings.</p>
      <p>
        <a href="/">Back to home</a>
      </p>
    </main>
  );
}
