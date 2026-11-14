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
    <main style={{ padding: 32, maxWidth: 1100, margin: "0 auto" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
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
