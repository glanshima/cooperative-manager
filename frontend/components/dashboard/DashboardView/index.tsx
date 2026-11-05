import StatusMessage from "@/components/ui/StatusMessage";
import type { DashboardPageModel } from "../hooks/useDashboardPage";
import ApplicationsSection from "../ApplicationsSection";
import ApplyForLoan from "../ApplyForLoan";
import LoansSection from "../LoansSection";
import RestrictionBanner from "../RestrictionBanner";

export default function DashboardView({ model }: { model: DashboardPageModel }) {
  return (
    <main style={{ padding: 32, maxWidth: 900, margin: "0 auto" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <h1>My Dashboard</h1>
        <button onClick={model.auth.logout}>Log out</button>
      </div>

      {model.member && (
        <p style={{ color: "#555" }}>
          {model.member.name} · PSN {model.member.psn}
        </p>
      )}

      {model.member?.loan_restricted && <RestrictionBanner settings={model.settings} />}

      {model.feedback.error && <StatusMessage tone="error">{model.feedback.error}</StatusMessage>}
      {model.feedback.success && (
        <StatusMessage tone="success">{model.feedback.success}</StatusMessage>
      )}

      <ApplyForLoan apply={model.apply} member={model.member} settings={model.settings} />
      <ApplicationsSection applications={model.applications} />
      <LoansSection loans={model.loans} />
    </main>
  );
}
