import StatusMessage from "@/components/ui/StatusMessage";
import type { DashboardPageModel } from "../hooks/useDashboardPage";
import ApplicationsSection from "../ApplicationsSection";
import ApplyForLoan from "../ApplyForLoan";
import ContributionCard from "../ContributionCard";
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

      {model.member && <ContributionCard member={model.member} />}

      {model.member?.loan_restricted && model.loansEnabled && (
        <RestrictionBanner settings={model.settings} />
      )}

      {model.feedback.error && <StatusMessage tone="error">{model.feedback.error}</StatusMessage>}
      {model.feedback.success && (
        <StatusMessage tone="success">{model.feedback.success}</StatusMessage>
      )}

      {model.loansEnabled ? (
        <>
          <ApplyForLoan apply={model.apply} member={model.member} settings={model.settings} />
          <ApplicationsSection applications={model.applications} />
          <LoansSection loans={model.loans} />
        </>
      ) : (
        <section style={{ marginTop: 24, padding: 16, border: "1px solid #ddd" }}>
          <h2>Loans module disabled</h2>
          <p>
            The Loans module has been disabled by an administrator. Loan applications and
            repayments are unavailable until it is re-enabled.
          </p>
        </section>
      )}
    </main>
  );
}
