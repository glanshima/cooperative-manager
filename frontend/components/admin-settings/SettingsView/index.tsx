import StatusMessage from "@/components/ui/StatusMessage";
import LogoutControl from "@/components/ui/LogoutControl";
import PageSkeleton from "@/components/ui/PageSkeleton";
import { PLATFORM_CREDIT } from "@/lib/branding";
import { hasPermission } from "@/lib/permissions";
import type { SettingsPageModel } from "../hooks/useSettingsPage";
import BrandingSection from "../BrandingSection";
import LoanApplicationSettingsSection from "../LoanApplicationSettingsSection";
import ModulesSection from "../ModulesSection";

export default function SettingsView({
  model,
  identity,
  permissions,
}: {
  model: SettingsPageModel;
  identity?: string | null;
  permissions: string[];
}) {
  if (model.loading || !model.settings) {
    return <PageSkeleton />;
  }

  const settings = model.settings;
  const canManageConfiguration = hasPermission(permissions, "admin.settings_manage");
  const canManageBranding = hasPermission(permissions, "branding.manage");
  const canViewBranding =
    canManageBranding || hasPermission(permissions, "branding.view");

  return (
    <main className="page page--700">
      <div className="page-header">
        <h1>Settings</h1>
        <LogoutControl identity={identity} onLogout={model.auth.logout} />
      </div>

      {model.feedback.error && (
        <StatusMessage tone="error">{model.feedback.error}</StatusMessage>
      )}
      {model.feedback.success && (
        <StatusMessage tone="success">{model.feedback.success}</StatusMessage>
      )}

      {canViewBranding && (
        <form onSubmit={model.saveBranding} style={{ display: "grid", gap: 16 }}>
          <BrandingSection
            settings={settings}
            setField={model.setField}
            readOnly={!canManageBranding}
          />
          {canManageBranding && <button type="submit">Save branding</button>}
        </form>
      )}

      {canManageConfiguration && (
        <form onSubmit={model.saveConfiguration} style={{ display: "grid", gap: 16 }}>
          <LoanApplicationSettingsSection settings={settings} setField={model.setField} />
          <ModulesSection settings={settings} setField={model.setField} />
          <button type="submit">Save settings</button>
        </form>
      )}

      <section style={{ marginTop: 32 }}>
        <h2>Platform</h2>
        <p style={{ color: "var(--text-muted)", fontSize: 14 }}>
          {PLATFORM_CREDIT}. Every screen credits the platform discreetly; the cooperative&apos;s
          own identity stays primary.
        </p>
      </section>
    </main>
  );
}
