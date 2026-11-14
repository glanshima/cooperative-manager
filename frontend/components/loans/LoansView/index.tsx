import StatusMessage from "@/components/ui/StatusMessage";
import LogoutControl from "@/components/ui/LogoutControl";
import type { LoansPageModel } from "../hooks/useLoansPage";
import DisburseLoanForm from "../DisburseLoanForm";
import LoansTable from "../LoansTable";
import LoanTypesManager from "../LoanTypesManager";

export default function LoansView({
  model,
  identity,
}: {
  model: LoansPageModel;
  identity?: string | null;
}) {
  return (
    <main className="page page--1100">
      <div className="page-header">
        <h1>Loans</h1>
        <LogoutControl identity={identity} onLogout={model.auth.logout} />
      </div>

      {model.feedback.error && (
        <StatusMessage tone="error">Error: {model.feedback.error}</StatusMessage>
      )}

      <section style={{ marginBottom: 16 }}>
        <button onClick={model.types.toggleManager}>
          {model.types.showManager ? "Hide" : "Manage"} loan types
        </button>
      </section>

      {model.types.showManager && <LoanTypesManager types={model.types} />}

      <DisburseLoanForm disburse={model.disburse} />
      <LoansTable table={model.table} />
    </main>
  );
}
