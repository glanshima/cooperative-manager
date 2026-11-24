import { useEffect, useState } from "react";

import { formatMoney } from "@/components/deductions/labels";
import {
  DividendAllocation,
  DividendAllocationPage,
  DividendManifest,
  DividendPayoutMethod,
  DividendRun,
  DividendRunDetail,
  DividendSummary,
  createDividendRun,
  declareDividendRun,
  deleteDividendRun,
  getDividendManifest,
  getDividendRun,
  getDividendSummary,
  listDividendAllocations,
  listDividendRuns,
  recomputeDividendRun,
  recordDividendPayout,
} from "@/lib/api";

import { todayIso } from "../labels";

export const ALLOCATION_PAGE_SIZE = 25;
const FEEDBACK_TIMEOUT_MS = 6000;

interface NewRunForm {
  open: boolean;
  fiscalYear: string;
  note: string;
}

interface DeclareForm {
  open: boolean;
  on: string;
}

interface PayoutForm {
  open: boolean;
  mode: "all" | "selected";
  paidOn: string;
  method: DividendPayoutMethod;
  reference: string;
  note: string;
}

export function useDividendsPage(permissions: string[]) {
  const can = (code: string) => permissions.includes(code);
  const canDeclare = can("dividend.declare");
  const canPay = can("dividend.pay");

  const [summary, setSummary] = useState<DividendSummary | null>(null);
  const [runs, setRuns] = useState<DividendRun[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);

  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<DividendRunDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);

  const [allocations, setAllocations] = useState<DividendAllocationPage | null>(null);
  const [allocationsLoading, setAllocationsLoading] = useState(false);
  const [search, setSearch] = useState("");
  const [appliedSearch, setAppliedSearch] = useState("");
  const [skip, setSkip] = useState(0);
  // Allocation id -> net amount, so the payout preview stays accurate even
  // when the selection spans pages.
  const [selected, setSelected] = useState<Record<string, string>>({});

  const [newRun, setNewRunState] = useState<NewRunForm>({
    open: false,
    fiscalYear: "",
    note: "",
  });
  const [declareForm, setDeclareFormState] = useState<DeclareForm>({ open: false, on: "" });
  const [payoutForm, setPayoutFormState] = useState<PayoutForm>({
    open: false,
    mode: "all",
    paidOn: "",
    method: "bank",
    reference: "",
    note: "",
  });
  const [manifest, setManifest] = useState<{ open: boolean; data: DividendManifest | null }>({
    open: false,
    data: null,
  });
  const [deleteTarget, setDeleteTarget] = useState<DividendRun | null>(null);

  useEffect(() => {
    if (!error) return;
    const timer = setTimeout(() => setError(null), FEEDBACK_TIMEOUT_MS);
    return () => clearTimeout(timer);
  }, [error]);

  useEffect(() => {
    if (!success) return;
    const timer = setTimeout(() => setSuccess(null), FEEDBACK_TIMEOUT_MS);
    return () => clearTimeout(timer);
  }, [success]);

  async function refresh() {
    const [nextSummary, nextRuns] = await Promise.all([getDividendSummary(), listDividendRuns()]);
    setSummary(nextSummary);
    setRuns(nextRuns);
  }

  useEffect(() => {
    let cancelled = false;
    refresh()
      .catch((e: any) => {
        if (!cancelled) setError(e.message);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function loadAllocations(runId: string, nextSkip: number, term: string) {
    setAllocationsLoading(true);
    try {
      setAllocations(
        await listDividendAllocations(runId, {
          q: term.trim() || undefined,
          skip: nextSkip,
          limit: ALLOCATION_PAGE_SIZE,
        })
      );
    } finally {
      setAllocationsLoading(false);
    }
  }

  async function openRun(id: string) {
    setSelectedId(id);
    setDetail(null);
    setDetailLoading(true);
    setSkip(0);
    setSearch("");
    setAppliedSearch("");
    setSelected({});
    try {
      const [nextDetail, nextAllocations] = await Promise.all([
        getDividendRun(id),
        listDividendAllocations(id, { skip: 0, limit: ALLOCATION_PAGE_SIZE }),
      ]);
      setDetail(nextDetail);
      setAllocations(nextAllocations);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setDetailLoading(false);
    }
  }

  function closeRun() {
    setSelectedId(null);
    setDetail(null);
    setAllocations(null);
    setSelected({});
    setSkip(0);
    setSearch("");
    setAppliedSearch("");
  }

  async function reloadSelectedRun() {
    if (!selectedId) return;
    await openRun(selectedId);
    await refresh();
  }

  const setNewRun = (patch: Partial<NewRunForm>) =>
    setNewRunState((current) => ({ ...current, ...patch }));
  const setDeclareForm = (patch: Partial<DeclareForm>) =>
    setDeclareFormState((current) => ({ ...current, ...patch }));
  const setPayoutForm = (patch: Partial<PayoutForm>) =>
    setPayoutFormState((current) => ({ ...current, ...patch }));

  function openNewRun() {
    setNewRun({ open: true, fiscalYear: String(summary?.suggested_fiscal_year ?? ""), note: "" });
  }

  async function submitNewRun() {
    const year = Number(newRun.fiscalYear);
    if (!Number.isInteger(year) || year < 2000 || year > 2100) {
      setError("Enter a fiscal year between 2000 and 2100.");
      return;
    }
    setBusy(true);
    try {
      const created = await createDividendRun({
        fiscal_year: year,
        note: newRun.note.trim() || undefined,
      });
      setNewRunState({ open: false, fiscalYear: "", note: "" });
      setSuccess(`Draft dividend run for ${created.fiscal_year} prepared.`);
      await refresh();
      await openRun(created.id);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function recompute() {
    if (!detail) return;
    setBusy(true);
    try {
      const run = await recomputeDividendRun(detail.run.id, detail.run.note ?? undefined);
      setSuccess(`Draft for ${run.fiscal_year} recomputed against the current settings and books.`);
      await reloadSelectedRun();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function confirmDelete() {
    if (!deleteTarget) return;
    setBusy(true);
    try {
      const year = deleteTarget.fiscal_year;
      await deleteDividendRun(deleteTarget.id);
      setDeleteTarget(null);
      if (selectedId === deleteTarget.id) closeRun();
      setSuccess(`Draft dividend run for ${year} deleted.`);
      await refresh();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  function openDeclare() {
    setDeclareForm({ open: true, on: todayIso() });
  }

  async function submitDeclare() {
    if (!detail) return;
    if (!declareForm.on) {
      setError("Choose the date the dividend is declared.");
      return;
    }
    setBusy(true);
    try {
      const year = detail.run.fiscal_year;
      await declareDividendRun(detail.run.id, declareForm.on);
      setDeclareFormState({ open: false, on: "" });
      setSuccess(`Dividend for ${year} declared and the fiscal year closed in the cashbook.`);
      await reloadSelectedRun();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  const payoutMethods: DividendPayoutMethod[] =
    summary?.payment_method === "bank"
      ? ["bank"]
      : summary?.payment_method === "cash"
        ? ["cash"]
        : ["bank", "cash"];

  function openPayout() {
    if (!detail) return;
    const hasSelection = Object.keys(selected).length > 0;
    setPayoutForm({
      open: true,
      mode: hasSelection ? "selected" : "all",
      paidOn: todayIso(),
      method: payoutMethods[0],
      reference: "",
      note: "",
    });
  }

  async function submitPayout() {
    if (!detail) return;
    const ids = Object.keys(selected);
    if (payoutForm.mode === "selected" && ids.length === 0) {
      setError("Select at least one allocation, or choose to pay all pending.");
      return;
    }
    if (!payoutForm.reference.trim()) {
      setError("Record the payment reference.");
      return;
    }
    setBusy(true);
    try {
      const recorded = await recordDividendPayout(detail.run.id, {
        paid_on: payoutForm.paidOn || undefined,
        method: payoutForm.method,
        reference: payoutForm.reference.trim(),
        note: payoutForm.note.trim() || undefined,
        allocation_ids: payoutForm.mode === "selected" ? ids : undefined,
      });
      setPayoutFormState((current) => ({ ...current, open: false }));
      setSelected({});
      setSuccess(`Payout of ₦${formatMoney(recorded.amount)} recorded as ${recorded.reference}.`);
      await reloadSelectedRun();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  function toggleSelected(allocation: DividendAllocation) {
    setSelected((current) => {
      const next = { ...current };
      if (next[allocation.id] !== undefined) {
        delete next[allocation.id];
      } else {
        next[allocation.id] = allocation.net_amount;
      }
      return next;
    });
  }

  function isSelected(id: string): boolean {
    return selected[id] !== undefined;
  }

  async function applySearch(term?: string) {
    if (!selectedId) return;
    const next = term ?? search;
    setSearch(next);
    setSkip(0);
    setAppliedSearch(next);
    try {
      await loadAllocations(selectedId, 0, next);
    } catch (e: any) {
      setError(e.message);
    }
  }

  async function changePage(nextSkip: number) {
    if (!selectedId) return;
    setSkip(nextSkip);
    try {
      await loadAllocations(selectedId, nextSkip, appliedSearch);
    } catch (e: any) {
      setError(e.message);
    }
  }

  async function openManifest() {
    if (!detail) return;
    setBusy(true);
    try {
      setManifest({ open: true, data: await getDividendManifest(detail.run.id) });
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  const paidSoFar = detail
    ? detail.payouts.reduce((sum, payout) => sum + Number(payout.amount), 0)
    : 0;
  const pendingAmount = detail ? Math.max(0, Number(detail.run.total_net) - paidSoFar) : 0;
  const selectedAmount = Object.values(selected).reduce((sum, value) => sum + Number(value), 0);
  const selectedCount = Object.keys(selected).length;

  return {
    permissions: { canDeclare, canPay },
    summary,
    runs,
    loading,
    busy,
    feedback: {
      error,
      success,
      dismissError: () => setError(null),
      dismissSuccess: () => setSuccess(null),
    },

    selectedId,
    detail,
    detailLoading,
    openRun,
    closeRun,

    allocations,
    allocationsLoading,
    search,
    setSearch,
    appliedSearch,
    skip,
    applySearch,
    changePage,
    selected,
    selectedCount,
    selectedAmount,
    toggleSelected,
    isSelected,

    newRun: { ...newRun, set: setNewRun },
    openNewRun,
    submitNewRun,

    recompute,

    declareForm: { ...declareForm, set: setDeclareForm },
    openDeclare,
    submitDeclare,

    payoutForm: { ...payoutForm, set: setPayoutForm },
    payoutMethods,
    pendingAmount,
    openPayout,
    submitPayout,

    manifest,
    closeManifest: () => setManifest({ open: false, data: null }),
    openManifest,

    deleteTarget,
    setDeleteTarget,
    confirmDelete,
  };
}

export type DividendsPageModel = ReturnType<typeof useDividendsPage>;
