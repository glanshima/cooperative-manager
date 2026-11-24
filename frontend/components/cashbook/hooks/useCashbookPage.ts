import { useEffect, useState } from "react";

import {
  CashbookAccountBalance,
  CashbookAccountKind,
  CashbookEntryPage,
  CashbookEntrySource,
  CashbookOverview,
  CashbookPeriodLock,
  createCashbookAccount,
  createCashbookEntry,
  getCashbookOverview,
  listCashbookAccounts,
  listCashbookEntries,
  listCashbookPeriodLocks,
  lockCashbookPeriod,
  postCashbookOpening,
  reverseCashbookEntry,
  unlockCashbookPeriod,
  updateCashbookAccount,
} from "@/lib/api";

import { emptyJournal, JournalLineDraft, journalLinesToInput } from "../journal";
import { monthStartIso, todayIso } from "../labels";

export type CashbookTab = "overview" | "journal" | "accounts" | "reports" | "locks";

export const ENTRY_PAGE_SIZE = 25;
const FEEDBACK_TIMEOUT_MS = 6000;

export interface CashbookFilters {
  start: string;
  end: string;
  source: CashbookEntrySource | "";
  accountId: string;
  q: string;
}

const EMPTY_FILTERS: CashbookFilters = { start: "", end: "", source: "", accountId: "", q: "" };

export function useCashbookPage(permissions: string[]) {
  const can = (code: string) => permissions.includes(code);

  const [tab, setTab] = useState<CashbookTab>("overview");
  const [overview, setOverview] = useState<CashbookOverview | null>(null);
  const [accounts, setAccounts] = useState<CashbookAccountBalance[]>([]);
  const [entries, setEntries] = useState<CashbookEntryPage | null>(null);
  const [locks, setLocks] = useState<CashbookPeriodLock[]>([]);
  const [loading, setLoading] = useState(true);
  const [entriesLoading, setEntriesLoading] = useState(false);

  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const [filters, setFilters] = useState<CashbookFilters>(EMPTY_FILTERS);
  const [skip, setSkip] = useState(0);

  const [opening, setOpening] = useState({
    open: false,
    asOf: todayIso(),
    note: "",
    lines: emptyJournal() as JournalLineDraft[],
  });
  const [entry, setEntry] = useState({
    open: false,
    entryDate: todayIso(),
    narration: "",
    reference: "",
    lines: emptyJournal() as JournalLineDraft[],
  });
  const [reversal, setReversal] = useState<{ entryId: string; narration: string; reason: string } | null>(
    null
  );
  const [accountForm, setAccountForm] = useState<{
    open: boolean;
    editingId: string | null;
    code: string;
    name: string;
    kind: CashbookAccountKind;
    description: string;
  }>({ open: false, editingId: null, code: "", name: "", kind: "expense", description: "" });
  const [lockForm, setLockForm] = useState({ month: monthStartIso().slice(0, 7), note: "" });

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

  async function loadOverview() {
    setOverview(await getCashbookOverview());
  }

  async function loadAccounts() {
    setAccounts(await listCashbookAccounts());
  }

  async function loadLocks() {
    setLocks(await listCashbookPeriodLocks());
  }

  async function loadEntries(nextSkip = skip, nextFilters = filters) {
    setEntriesLoading(true);
    try {
      setEntries(
        await listCashbookEntries({
          start: nextFilters.start || undefined,
          end: nextFilters.end || undefined,
          source: nextFilters.source || undefined,
          account_id: nextFilters.accountId || undefined,
          q: nextFilters.q.trim() || undefined,
          skip: nextSkip,
          limit: ENTRY_PAGE_SIZE,
        })
      );
    } catch (e: any) {
      setError(e.message);
    } finally {
      setEntriesLoading(false);
    }
  }

  async function refresh() {
    try {
      await Promise.all([loadOverview(), loadAccounts(), loadLocks()]);
    } catch (e: any) {
      setError(e.message);
    }
  }

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [nextOverview, nextAccounts, nextLocks] = await Promise.all([
          getCashbookOverview(),
          listCashbookAccounts(),
          listCashbookPeriodLocks(),
        ]);
        if (cancelled) return;
        setOverview(nextOverview);
        setAccounts(nextAccounts);
        setLocks(nextLocks);
      } catch (e: any) {
        if (!cancelled) setError(e.message);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (loading) return;
    void loadEntries(skip, filters);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loading, skip, filters.start, filters.end, filters.source, filters.accountId, filters.q]);

  function changeFilters(patch: Partial<CashbookFilters>) {
    setSkip(0);
    setFilters((current) => ({ ...current, ...patch }));
  }

  async function submitOpening() {
    setError(null);
    setSuccess(null);
    const built = journalLinesToInput(opening.lines);
    if (!built.ok) {
      setError(built.error);
      return;
    }
    setBusy(true);
    try {
      await postCashbookOpening({
        as_of: opening.asOf,
        note: opening.note.trim() || undefined,
        lines: built.lines,
      });
      setSuccess("Opening balances posted. Automatic postings can now run.");
      setOpening({ open: false, asOf: todayIso(), note: "", lines: emptyJournal() });
      await refresh();
      setSkip(0);
      await loadEntries(0, filters);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function submitEntry() {
    setError(null);
    setSuccess(null);
    if (!entry.narration.trim()) {
      setError("Give the entry a narration so the book explains itself.");
      return;
    }
    const built = journalLinesToInput(entry.lines);
    if (!built.ok) {
      setError(built.error);
      return;
    }
    setBusy(true);
    try {
      await createCashbookEntry({
        entry_date: entry.entryDate,
        narration: entry.narration.trim(),
        reference: entry.reference.trim() || undefined,
        lines: built.lines,
      });
      setSuccess("Entry posted.");
      setEntry({ open: false, entryDate: todayIso(), narration: "", reference: "", lines: emptyJournal() });
      await refresh();
      setSkip(0);
      await loadEntries(0, filters);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function submitReversal() {
    if (!reversal) return;
    setError(null);
    setSuccess(null);
    if (!reversal.reason.trim()) {
      setError("Say why this entry is being reversed.");
      return;
    }
    setBusy(true);
    try {
      await reverseCashbookEntry(reversal.entryId, { reason: reversal.reason.trim() });
      setSuccess("Reversal posted. The original entry stays in the history.");
      setReversal(null);
      await refresh();
      await loadEntries();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function submitAccount() {
    setError(null);
    setSuccess(null);
    const name = accountForm.name.trim();
    if (!name) {
      setError("Give the account a name.");
      return;
    }
    setBusy(true);
    try {
      if (accountForm.editingId) {
        await updateCashbookAccount(accountForm.editingId, {
          name,
          description: accountForm.description.trim() || null,
        });
        setSuccess("Account updated.");
      } else {
        const code = accountForm.code.trim();
        if (!code) {
          setError("Give the account a code.");
          setBusy(false);
          return;
        }
        await createCashbookAccount({
          code,
          name,
          kind: accountForm.kind,
          description: accountForm.description.trim() || undefined,
        });
        setSuccess("Account added to the chart.");
      }
      setAccountForm({ open: false, editingId: null, code: "", name: "", kind: "expense", description: "" });
      await refresh();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function setAccountActive(account: CashbookAccountBalance, isActive: boolean) {
    setError(null);
    setSuccess(null);
    setBusy(true);
    try {
      await updateCashbookAccount(account.id, { is_active: isActive });
      setSuccess(isActive ? `${account.code} reactivated.` : `${account.code} deactivated.`);
      await refresh();
      await loadEntries();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function lockMonth() {
    setError(null);
    setSuccess(null);
    if (!lockForm.month) {
      setError("Choose the month to lock.");
      return;
    }
    setBusy(true);
    try {
      await lockCashbookPeriod({ period_start: `${lockForm.month}-01`, note: lockForm.note.trim() || undefined });
      setSuccess(`${lockForm.month} is now locked.`);
      setLockForm({ month: monthStartIso().slice(0, 7), note: "" });
      await refresh();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function unlockMonth(periodStart: string) {
    setError(null);
    setSuccess(null);
    setBusy(true);
    try {
      await unlockCashbookPeriod(periodStart);
      setSuccess(`${periodStart.slice(0, 7)} unlocked.`);
      await refresh();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  return {
    tab,
    setTab,
    loading,
    entriesLoading,
    overview,
    accounts,
    activeAccounts: accounts.filter((account) => account.is_active),
    entries,
    locks,
    busy,
    feedback: {
      error,
      success,
      dismissError: () => setError(null),
      dismissSuccess: () => setSuccess(null),
    },
    permissions: {
      canPost: can("accounting.post"),
      canAdjust: can("accounting.adjust"),
      canReverse: can("accounting.reverse"),
      canReconcile: can("accounting.reconcile"),
    },
    permissionCodes: permissions,
    filters: {
      value: filters,
      change: changeFilters,
      reset: () => {
        setSkip(0);
        setFilters(EMPTY_FILTERS);
      },
    },
    paging: {
      skip,
      limit: ENTRY_PAGE_SIZE,
      total: entries?.total ?? 0,
      goToPage: (nextSkip: number) => setSkip(nextSkip),
    },
    opening: { ...opening, set: setOpening, submit: submitOpening },
    entry: { ...entry, set: setEntry, submit: submitEntry },
    reversal: {
      value: reversal,
      request: (target: { entryId: string; narration: string }) =>
        setReversal({ ...target, reason: "" }),
      setReason: (reason: string) =>
        setReversal((current) => (current ? { ...current, reason } : current)),
      cancel: () => setReversal(null),
      submit: submitReversal,
    },
    accountForm: { ...accountForm, set: setAccountForm, submit: submitAccount },
    setAccountActive,
    lockForm: { ...lockForm, set: setLockForm },
    lockMonth,
    unlockMonth,
    refresh,
  };
}

export type CashbookPageModel = ReturnType<typeof useCashbookPage>;
