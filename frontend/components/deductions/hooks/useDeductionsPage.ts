import { useEffect, useState } from "react";

import {
  bulkDeductions,
  confirmDeduction,
  createDeduction,
  getDeductionSchedule,
  listDeductions,
  listLoans,
  listMembers,
  markDeductionNotDeducted,
  returnDeductionToDraft,
  submitDeduction,
  updateDeduction,
  voidDeduction,
} from "@/lib/api";
import type {
  Loan,
  Member,
  PayrollDeduction,
  PayrollDeductionBulkAction,
  PayrollDeductionCreateInput,
  PayrollDeductionSchedule,
  PayrollDeductionStatus,
  PayrollDeductionUpdateInput,
} from "@/lib/api";

import { currentMonth } from "../labels";

export type DeductionActionKind = "submit" | "return_to_draft" | "confirm" | "not_deducted" | "void";

const ACTION_LABELS: Record<DeductionActionKind, string> = {
  submit: "Submit",
  return_to_draft: "Return to draft",
  confirm: "Confirm deduction",
  not_deducted: "Mark not deducted",
  void: "Void",
};

const BULK_ACTION_NAMES: Partial<Record<DeductionActionKind, PayrollDeductionBulkAction>> = {
  submit: "submit",
  confirm: "confirm",
  not_deducted: "not-deducted",
  void: "void",
};

const REASON_ACTIONS = new Set<DeductionActionKind>(["return_to_draft", "not_deducted", "void"]);

export function useDeductionsPage(logout: () => void) {
  const [month, setMonth] = useState(currentMonth());
  const [status, setStatus] = useState<PayrollDeductionStatus | "all">("all");

  const [items, setItems] = useState<PayrollDeduction[]>([]);
  const [schedule, setSchedule] = useState<PayrollDeductionSchedule | null>(null);
  const [members, setMembers] = useState<Member[]>([]);
  const [loans, setLoans] = useState<Loan[]>([]);

  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const [selected, setSelected] = useState<string[]>([]);
  const [editing, setEditing] = useState<PayrollDeduction | null>(null);
  const [formOpen, setFormOpen] = useState(false);

  const [pending, setPending] = useState<{ action: DeductionActionKind; ids: string[] } | null>(null);
  const [reason, setReason] = useState("");

  const [printMode, setPrintMode] = useState(false);

  async function refresh() {
    setLoading(true);
    setError(null);
    try {
      const [records, monthSchedule] = await Promise.all([
        listDeductions({ month, status: status === "all" ? undefined : status }),
        getDeductionSchedule(month),
      ]);
      setItems(records);
      setSchedule(monthSchedule);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [month, status]);

  // Member and active-loan lookups make the entry form usable, but the
  // deductions list itself must still work when the Members or Loans
  // module is disabled (and those routes 403).
  useEffect(() => {
    let cancelled = false;
    Promise.allSettled([listMembers({ limit: 1000 }), listLoans()]).then(([memberResult, loanResult]) => {
      if (cancelled) return;
      if (memberResult.status === "fulfilled") setMembers(memberResult.value.items);
      if (loanResult.status === "fulfilled") setLoans(loanResult.value);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  async function runAction(action: DeductionActionKind, ids: string[], reasonText?: string) {
    if (!ids.length) return;
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      let successText: string;
      let failureText: string | null = null;

      if (ids.length === 1) {
        const id = ids[0];
        if (action === "submit") await submitDeduction(id);
        else if (action === "confirm") await confirmDeduction(id);
        else if (action === "return_to_draft") await returnDeductionToDraft(id, reasonText || "");
        else if (action === "not_deducted") await markDeductionNotDeducted(id, reasonText || "");
        else await voidDeduction(id, reasonText || "");
        successText = `${ACTION_LABELS[action]} completed.`;
      } else if (action === "return_to_draft") {
        for (const id of ids) await returnDeductionToDraft(id, reasonText || "");
        successText = `Returned ${ids.length} deductions to draft.`;
      } else {
        const response = await bulkDeductions(BULK_ACTION_NAMES[action]!, ids, reasonText);
        const failed = response.results.filter((result) => !result.ok);
        successText = `${ids.length - failed.length} of ${ids.length} deductions updated.`;
        if (failed.length) {
          failureText =
            failed
              .map((result) => result.detail)
              .filter(Boolean)
              .join("; ") || "Some deductions could not be updated.";
        }
      }

      setPending(null);
      setSelected([]);
      await refresh();
      // Refresh clears the error banner, so surface partial failures only
      // after it has finished.
      setMessage(successText);
      setError(failureText);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  function requestAction(action: DeductionActionKind, ids: string[]) {
    if (!ids.length) return;
    if (REASON_ACTIONS.has(action)) {
      setPending({ action, ids });
      setReason("");
      return;
    }
    runAction(action, ids);
  }

  function confirmPendingAction() {
    if (!pending) return;
    const trimmed = reason.trim();
    if (!trimmed) {
      setError("A reason is required for this action.");
      return;
    }
    runAction(pending.action, pending.ids, trimmed);
  }

  function cancelPendingAction() {
    setPending(null);
    setReason("");
  }

  function toggleSelected(id: string) {
    setSelected((current) =>
      current.includes(id) ? current.filter((value) => value !== id) : [...current, id]
    );
  }

  function toggleAll(ids: string[]) {
    setSelected((current) => (ids.every((id) => current.includes(id)) ? [] : ids));
  }

  function clearSelection() {
    setSelected([]);
  }

  function openCreate() {
    setEditing(null);
    setFormOpen(true);
    setError(null);
    setMessage(null);
  }

  function openEdit(deduction: PayrollDeduction) {
    setEditing(deduction);
    setFormOpen(true);
    setError(null);
    setMessage(null);
  }

  function closeForm() {
    setEditing(null);
    setFormOpen(false);
  }

  async function saveDraft(
    input: PayrollDeductionCreateInput | PayrollDeductionUpdateInput,
    id?: string
  ) {
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      if (id) await updateDeduction(id, input as PayrollDeductionUpdateInput);
      else await createDeduction(input as PayrollDeductionCreateInput);
      closeForm();
      setMessage(id ? "Draft updated." : "Draft created.");
      await refresh();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  function loansForMember(memberId: string): Loan[] {
    return loans.filter((loan) => loan.member_id === memberId && loan.status === "active");
  }

  return {
    auth: { logout },
    feedback: { error, message, busy },
    filters: { month, setMonth, status, setStatus },
    table: {
      items,
      loading,
      selected,
      toggleSelected,
      toggleAll,
      clearSelection,
    },
    totals: schedule?.totals ?? null,
    schedule,
    actions: {
      request: requestAction,
      pending,
      reason,
      setReason,
      confirmPending: confirmPendingAction,
      cancelPending: cancelPendingAction,
    },
    form: {
      open: formOpen,
      editing,
      members,
      loansForMember,
      openCreate,
      openEdit,
      close: closeForm,
      save: saveDraft,
    },
    print: {
      mode: printMode,
      open: () => setPrintMode(true),
      close: () => setPrintMode(false),
    },
  };
}

export type DeductionsPageModel = ReturnType<typeof useDeductionsPage>;
