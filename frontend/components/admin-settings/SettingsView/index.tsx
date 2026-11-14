import StatusMessage from "@/components/ui/StatusMessage";
import LogoutControl from "@/components/ui/LogoutControl";
import type { SettingsPageModel } from "../hooks/useSettingsPage";
import LoanApplicationSettingsSection from "../LoanApplicationSettingsSection";
import ModulesSection from "../ModulesSection";

export default function SettingsView({
  model,
  identity,
}: {
  model: SettingsPageModel;
  identity?: string | null;
}) {
  if (model.loading || !model.settings) {
    return <main style={{ padding: 32 }}>Loading...</main>;
  }

  const settings = model.settings;

  return (
    <main style={{ padding: 32, maxWidth: 700, margin: "0 auto" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <h1>Settings</h1>
        <LogoutControl identity={identity} onLogout={model.auth.logout} />
      </div>

      {model.feedback.error && (
        <StatusMessage tone="error">{model.feedback.error}</StatusMessage>
      )}
      {model.feedback.success && (
        <StatusMessage tone="success">{model.feedback.success}</StatusMessage>
      )}

      <form onSubmit={model.save} style={{ display: "grid", gap: 16 }}>
        <LoanApplicationSettingsSection settings={settings} setField={model.setField} />
        <ModulesSection settings={settings} setField={model.setField} />
        <button type="submit">Save settings</button>
      </form>
    </main>
  );
}
