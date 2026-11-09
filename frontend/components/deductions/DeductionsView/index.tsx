import StatusMessage from "@/components/ui/StatusMessage";

import BulkActionsBar from "../BulkActionsBar";
import DeductionFilters from "../DeductionFilters";
import DeductionForm from "../DeductionForm";
import DeductionWorklist from "../DeductionWorklist";
import DeductionsTable from "../DeductionsTable";
import PrintableSchedule from "../PrintableSchedule";
import ReasonDialog from "../ReasonDialog";
import type { DeductionActionKind, DeductionsPageModel } from "../hooks/useDeductionsPage";

const PENDING_COPY: Record<DeductionActionKind, { title: string; description: string }> = {
  submit: {
    title: "Submit deductions",
    description: "Submit the selected draft deductions for payroll.",
  },
  confirm: {
    title: "Confirm deductions",
    description: "Confirm the selected deductions were deducted and remitted.",
  },
  return_to_draft: {
    title: "Return to draft",
    description: "Send this record back for correction. Explain what needs to change.",
  },
  not_deducted: {
    title: "Mark as not deducted",
    description:
      "Payroll did not effect this deduction. The member must pay by bank/cash and submit repayment evidence instead. Enter a reason for the record.",
  },
  void: {
    title: "Void deduction",
    description:
      "Voiding removes this record from the active schedule. If it was already confirmed, the loan credits it applied are reversed and any loan it completed is reopened. Enter a reason.",
  },
};

export default function DeductionsView({ model }: { model: DeductionsPageModel }) {
  if (model.print.mode) {
    return <PrintableSchedule schedule={model.schedule} onClose={model.print.close} />;
  }

  const busy = model.feedback.busy;
  const pending = model.actions.pending;
  const pendingCopy = pending ? PENDING_COPY[pending.action] : null;

  return (
    <main style={{ padding: 32, maxWidth: 1200, margin: "0 auto" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <h1>Payroll Deductions</h1>
        <button onClick={model.auth.logout}>Log out</button>
      </div>

      {model.feedback.error && (
        <StatusMessage tone="error">{model.feedback.error}</StatusMessage>
      )}
      {model.feedback.message && (
        <StatusMessage tone="success">{model.feedback.message}</StatusMessage>
      )}

      <div role="tablist" aria-label="Deductions view" style={{ display: "flex", gap: 8, marginBottom: 16 }}>
        <button
          role="tab"
          aria-selected={model.tab === "enter"}
          onClick={() => model.setTab("enter")}
          style={{ fontWeight: model.tab === "enter" ? 700 : 400 }}
        >
          Enter
        </button>
        <button
          role="tab"
          aria-selected={model.tab === "ledger"}
          onClick={() => model.setTab("ledger")}
          style={{ fontWeight: model.tab === "ledger" ? 700 : 400 }}
        >
          Ledger
        </button>
      </div>

      {model.form.open && (
        <DeductionForm
          key={model.form.editing?.id ?? model.form.prefill?.memberId ?? "new"}
          form={model.form}
          busy={busy}
        />
      )}

      {model.tab === "enter" ? (
        <DeductionWorklist
          worklist={model.worklist}
          month={model.filters.month}
          setMonth={model.filters.setMonth}
          onAddAny={model.form.openCreate}
          busy={busy}
        />
      ) : (
        <>
          <DeductionFilters
            filters={model.filters}
            totals={model.totals}
            onCreate={model.form.openCreate}
            onPrint={model.print.open}
          />

          <BulkActionsBar
            count={model.table.selected.length}
            busy={busy}
            onAction={(action) => model.actions.request(action, model.table.selected)}
            onClear={model.table.clearSelection}
          />

          {model.table.loading ? <p>Loading...</p> : null}
          {!model.table.loading && (
            <DeductionsTable
              table={model.table}
              actions={model.actions}
              busy={busy}
              onEdit={model.form.openEdit}
            />
          )}
        </>
      )}

      {pending && pendingCopy && (
        <ReasonDialog
          title={pendingCopy.title}
          description={pendingCopy.description}
          reason={model.actions.reason}
          setReason={model.actions.setReason}
          onConfirm={model.actions.confirmPending}
          onCancel={model.actions.cancelPending}
          busy={busy}
        />
      )}
    </main>
  );
}
