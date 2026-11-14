import StatusMessage from "@/components/ui/StatusMessage";
import DashboardHeader from "@/components/ui/DashboardHeader";
import { lastNameFirst, userDisplayName } from "@/lib/names";
import type { DashboardPageModel } from "../hooks/useDashboardPage";
import ApplicationsSection from "../ApplicationsSection";
import ApplyForLoan from "../ApplyForLoan";
import ContributionCard from "../ContributionCard";
import LoansSection from "../LoansSection";
import RestrictionBanner from "../RestrictionBanner";

export default function DashboardView({ model }: { model: DashboardPageModel }) {
  const displayName = model.member ? lastNameFirst(model.member.name) : null;

  return (
    <main style={{ padding: 32, maxWidth: 900, margin: "0 auto" }}>
      <DashboardHeader
        name={displayName}
        fallbackTitle="My Dashboard"
        identity={displayName ?? userDisplayName(model.auth.user)}
        onLogout={model.auth.logout}
      />

      {model.member && (
        <p style={{ color: "#555" }}>PSN {model.member.psn?.replace("MCT-", "") ?? ""}</p>
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
