import { useEffect, useState } from "react";

import {
  BULK_CHUNK_SIZE,
  LEDGER_PAGE_SIZE,
  bulkDeductions,
  confirmDeduction,
  createDeduction,
  getDeductionSchedule,
  getDeductionWorklist,
  getSubmittableDeductionIds,
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
  DeductionWorklistItem,
  DeductionWorklistOut,
  Loan,
  Member,
  MemberStatus,
  PayrollDeduction,
  PayrollDeductionBulkAction,
  PayrollDeductionCreateInput,
  PayrollDeductionSchedule,
  PayrollDeductionStatus,
  PayrollDeductionUpdateInput,
} from "@/lib/api";

import { currentMonth } from "@/lib/month";

export type DeductionActionKind = "submit" | "return_to_draft" | "confirm" | "not_deducted" | "void";

export type DeductionsTab = "enter" | "ledger";

// What the Enter queue hands the form when an officer clicks a due member:
// the server's expected amounts, so the form opens filled rather than blank.
export interface DeductionPrefill {
  memberId: string;
  memberName: string;
  memberStatus: MemberStatus;
  month: string; // YYYY-MM
  contribution: string;
  loanLines: { loanId: string; label: string; amount: string }[];
  conflicted: boolean;
}

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
  const [total, setTotal] = useState(0);
  const [skip, setSkip] = useState(0);
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
  const [submitAll, setSubmitAll] = useState<{
    month: string;
    ids: string[];
    emptyCount: number;
  } | null>(null);

  const [printMode, setPrintMode] = useState(false);

  const [tab, setTab] = useState<DeductionsTab>("enter");
  const [worklist, setWorklist] = useState<DeductionWorklistOut | null>(null);
  const [worklistLoading, setWorklistLoading] = useState(true);
  const [worklistError, setWorklistError] = useState<string | null>(null);
  const [includeEntered, setIncludeEntered] = useState(false);
  const [prefill, setPrefill] = useState<DeductionPrefill | null>(null);
  const [lastEntered, setLastEntered] = useState<{ id: string; memberName: string } | null>(null);

  async function refresh(overrides: { skip?: number } = {}) {
    const effectiveSkip = overrides.skip !== undefined ? overrides.skip : skip;
    setLoading(true);
    setError(null);
    try {
      const [page, monthSchedule] = await Promise.all([
        listDeductions({
          month,
          status: status === "all" ? undefined : status,
          skip: effectiveSkip,
          limit: LEDGER_PAGE_SIZE,
        }),
        getDeductionSchedule(month),
      ]);
      setItems(page.items);
      setTotal(page.total);
      setSkip(page.skip);
      setSchedule(monthSchedule);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  function goToPage(newSkip: number) {
    if (newSkip < 0 || newSkip >= total) return;
    // Selection is page-scoped: carrying ids from a page that is no longer
    // on screen would invite acting on records the officer cannot see.
    setSelected([]);
    refresh({ skip: newSkip });
  }

  useEffect(() => {
    // Every filter change starts back at page 1.
    refresh({ skip: 0 });
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

  async function refreshWorklist() {
    setWorklistLoading(true);
    setWorklistError(null);
    try {
      setWorklist(await getDeductionWorklist(month, includeEntered));
    } catch (e: any) {
      setWorklistError(e.message);
    } finally {
      setWorklistLoading(false);
    }
  }

  useEffect(() => {
    refreshWorklist();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [month, includeEntered]);

  // Each bulk call commits every record it accepts as it goes, so a call
  // that outlives the server's function timeout would leave a batch half
  // applied with no report at all. Chunks keep each request short and make
  // sure every id comes back with a verdict.
  async function runBulkChunked(
    actionName: PayrollDeductionBulkAction,
    ids: string[],
    reasonText?: string
  ): Promise<{ succeeded: number; failures: string[] }> {
    const reasons = new Map<string, number>();
    let succeeded = 0;

    for (let index = 0; index < ids.length; index += BULK_CHUNK_SIZE) {
      const chunk = ids.slice(index, index + BULK_CHUNK_SIZE);
      const response = await bulkDeductions(actionName, chunk, reasonText);
      const failed = response.results.filter((result) => !result.ok);
      succeeded += response.results.length - failed.length;
      for (const result of failed) {
        const detail = result.detail || "No reason given";
        reasons.set(detail, (reasons.get(detail) ?? 0) + 1);
      }
    }

    const failures = [...reasons.entries()].map(
      ([detail, count]) => (count > 1 ? `${detail} (×${count})` : detail)
    );
    return { succeeded, failures };
  }

  async function requestSubmitAll() {
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      // Scope comes from the server: the ledger only holds one page, so the
      // rows on screen cannot answer "which drafts exist this month".
      const scope = await getSubmittableDeductionIds(month);

      if (!scope.ids.length) {
        setMessage(
          scope.empty_draft_ids.length
            ? `Nothing to submit for ${month}: ${scope.empty_draft_ids.length} draft(s) have no lines yet.`
            : `No draft deductions to submit for ${month}.`
        );
        return;
      }
      // Held back for confirmation so the officer sees the real count and
      // the exclusions before anything moves.
      setSubmitAll({ month, ids: scope.ids, emptyCount: scope.empty_draft_ids.length });
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function confirmSubmitAll() {
    if (!submitAll) return;
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      const { succeeded, failures } = await runBulkChunked("submit", submitAll.ids);
      const parts = [`${succeeded} of ${submitAll.ids.length} drafts submitted`];
      if (submitAll.emptyCount) {
        parts.push(`${submitAll.emptyCount} left as drafts (no lines)`);
      }
      if (failures.length) parts.push(`${submitAll.ids.length - succeeded} refused`);
      setMessage(parts.join(" · "));

      setSubmitAll(null);
      setSelected([]);
      await refresh();
      await refreshWorklist();
      if (failures.length) setError(failures.join("; "));
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  function cancelSubmitAll() {
    setSubmitAll(null);
  }

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
        const { succeeded, failures } = await runBulkChunked(
          BULK_ACTION_NAMES[action]!,
          ids,
          reasonText
        );
        successText = `${succeeded} of ${ids.length} deductions updated.`;
        if (failures.length) failureText = failures.join("; ");
      }

      setPending(null);
      setSelected([]);
      await refresh();
      await refreshWorklist();
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
    setPrefill(null);
    setFormOpen(true);
    setError(null);
    setMessage(null);
  }

  function openEdit(deduction: PayrollDeduction) {
    setEditing(deduction);
    setPrefill(null);
    setFormOpen(true);
    setError(null);
    setMessage(null);
  }

  // Clicking a due member in the Enter queue opens the form filled with the
  // server's expected amounts instead of a blank entry the officer has to
  // compute by hand.
  function openFromWorklist(item: DeductionWorklistItem) {
    const contributionLine = item.lines.find((line) => line.category === "monthly_contribution");
    setEditing(null);
    setPrefill({
      memberId: item.member_id,
      memberName: item.member_name,
      memberStatus: item.member_status,
      month,
      contribution: contributionLine?.amount ?? "",
      loanLines: item.lines
        .filter((line) => line.category === "loan_repayment" && line.loan_id)
        .map((line) => ({
          loanId: line.loan_id!,
          label: line.loan_type_name ?? "Loan",
          amount: line.amount,
        })),
      conflicted: item.conflicted,
    });
    setFormOpen(true);
    setError(null);
    setMessage(null);
  }

  function closeForm() {
    setEditing(null);
    setPrefill(null);
    setFormOpen(false);
  }

  async function saveDraft(
    input: PayrollDeductionCreateInput | PayrollDeductionUpdateInput,
    id?: string
  ) {
    setBusy(true);
    setError(null);
    setMessage(null);
    // Capture before closeForm clears it: a draft created from the queue
    // offers a one-click undo (void) while it is still unconfirmed.
    const enteredFromQueue = prefill;
    try {
      if (id) {
        await updateDeduction(id, input as PayrollDeductionUpdateInput);
        closeForm();
        setMessage("Draft updated.");
      } else {
        const created = await createDeduction(input as PayrollDeductionCreateInput);
        closeForm();
        setMessage("Draft created.");
        if (enteredFromQueue) {
          setLastEntered({ id: created.id, memberName: enteredFromQueue.memberName });
        }
      }
      await refresh();
      await refreshWorklist();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function undoLastEntered() {
    if (!lastEntered) return;
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      await voidDeduction(lastEntered.id, "Entered in error");
      setMessage(`Entry for ${lastEntered.memberName} undone.`);
      setLastEntered(null);
      await refresh();
      await refreshWorklist();
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
    tab,
    setTab,
    worklist: {
      data: worklist,
      loading: worklistLoading,
      error: worklistError,
      includeEntered,
      setIncludeEntered,
      refresh: refreshWorklist,
      openItem: openFromWorklist,
      lastEntered,
      undo: undoLastEntered,
    },
    table: {
      items,
      loading,
      selected,
      toggleSelected,
      toggleAll,
      clearSelection,
      pagination: { skip, limit: LEDGER_PAGE_SIZE, total, goToPage },
    },
    totals: schedule?.totals ?? null,
    schedule,
    actions: {
      request: requestAction,
      submitAll: {
        preview: submitAll,
        request: requestSubmitAll,
        confirm: confirmSubmitAll,
        cancel: cancelSubmitAll,
      },
      pending,
      reason,
      setReason,
      confirmPending: confirmPendingAction,
      cancelPending: cancelPendingAction,
    },
    form: {
      open: formOpen,
      editing,
      prefill,
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
