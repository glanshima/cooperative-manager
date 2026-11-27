import PlatformAttribution from "@/components/branding/PlatformAttribution";
import StatusMessage from "@/components/ui/StatusMessage";
import { lastNameFirst } from "@/lib/names";
import type { DashboardPageModel } from "../hooks/useDashboardPage";
import AccountOverview from "../AccountOverview";
import ApplicationsSection from "../ApplicationsSection";
import ApplyForLoan from "../ApplyForLoan";
import ContributionCard from "../ContributionCard";
import LoansSection from "../LoansSection";
import MembershipCard from "../MembershipCard";
import MemberShell from "../MemberShell";
import NotificationPreferencesCard from "../NotificationPreferences";
import NotificationsCard from "../NotificationsCard";
import QuickLinks from "../QuickLinks";
import RecentActivity from "../RecentActivity";
import RestrictionBanner from "../RestrictionBanner";
import SummaryCards from "../SummaryCards";
import DashboardIcon from "../icons";

import styles from "../dashboard.module.css";

export default function DashboardView({ model }: { model: DashboardPageModel }) {
  const { member, summary, auth } = model;
  const displayName = member ? lastNameFirst(member.name) : null;
  const today = new Date().toLocaleDateString(undefined, {
    weekday: "long",
    day: "numeric",
    month: "long",
    year: "numeric",
  });

  return (
    <MemberShell member={member} user={auth.user} onLogout={auth.logout}>
      <main className={styles.content}>
        <div id="overview" className={`${styles.welcome} ${styles.anchor}`}>
          <div>
            <h1 className={styles.welcomeTitle}>
              {displayName ? `Welcome, ${displayName}` : "My Dashboard"}
            </h1>
            <p className={styles.welcomeNote}>
              Your savings, loans and payroll deductions at a glance.
            </p>
          </div>
          <span className={styles.dateChip}>
            <DashboardIcon name="calendar" size={16} />
            {today}
          </span>
        </div>

        {model.feedback.error && <StatusMessage tone="error">{model.feedback.error}</StatusMessage>}
        {model.feedback.success && (
          <StatusMessage tone="success">{model.feedback.success}</StatusMessage>
        )}

        {member && (
          <>
            <SummaryCards
              savings={summary.savings}
              loanBalance={summary.loanBalance}
              deductions={summary.deductions}
              loansEnabled={model.loansEnabled}
              deductionsEnabled={model.deductionsEnabled}
            />

            <div className={styles.split}>
              <div className={styles.stack}>
                <AccountOverview
                  savings={summary.savings}
                  loanBalance={summary.loanBalance}
                  loansEnabled={model.loansEnabled}
                />
                <RecentActivity items={summary.activity} />
              </div>
              <div className={styles.stack}>
                <MembershipCard member={member} />
                <QuickLinks
                  loansEnabled={model.loansEnabled}
                  onApplyForLoan={() => {
                    if (!model.apply.showForm) model.apply.toggle();
                  }}
                />
                <NotificationsCard page={summary.notifications} />
              </div>
            </div>
          </>
        )}

        {member?.loan_restricted && model.loansEnabled && (
          <RestrictionBanner settings={model.settings} />
        )}

        <section id="savings" className={`${styles.section} ${styles.anchor}`}>
          {member ? (
            <ContributionCard member={member} />
          ) : (
            <p className={styles.empty}>Your member record could not be loaded.</p>
          )}
        </section>

        <section id="loans" className={`${styles.section} ${styles.anchor}`}>
          <h2 className={styles.sectionTitle}>Loans</h2>
          {model.loansEnabled ? (
            <>
              <ApplyForLoan apply={model.apply} member={member} />
              <ApplicationsSection applications={model.applications} />
              <LoansSection loans={model.loans} />
            </>
          ) : (
            <div className={styles.disabledPanel}>
              <h2>Loans module disabled</h2>
              <p>
                The Loans module has been disabled by an administrator. Loan applications and
                repayments are unavailable until it is re-enabled.
              </p>
            </div>
          )}
        </section>

        {member && (
          <section id="preferences" className={`${styles.section} ${styles.anchor}`}>
            <NotificationPreferencesCard />
          </section>
        )}

        {!member && (
          <div className={styles.panel} style={{ marginTop: 22 }}>
            <h2 className={styles.panelTitle}>Member record unavailable</h2>
            <p className={styles.panelNote}>
              We could not load your membership details. Refresh the page or contact the office.
            </p>
          </div>
        )}

        <footer className={styles.footer}>
          <PlatformAttribution />
        </footer>
      </main>
    </MemberShell>
  );
}
