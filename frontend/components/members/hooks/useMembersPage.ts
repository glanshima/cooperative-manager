import { useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";

import {
  Member,
  MemberInput,
  MemberFilterOptions,
  MemberStatus,
  listMembers,
  getMemberFilterOptions,
  createMember,
  updateMember,
  deleteMember,
  createMemberLogin,
  updateMemberLoginStatus,
  withdrawMember,
} from "@/lib/api";
import {
  ContributionChangeRequest,
  listContributionChangeRequests,
  approveContributionChangeRequest,
  rejectContributionChangeRequest,
} from "@/lib/api/contributions";

import type { NokMemberOption } from "../types";
import { describeError } from "../utils";

export const PAGE_SIZE = 25;

const EMPTY_FORM: MemberInput = {
  psn: "",
  name: "",
  bank_name: "",
  account_number: "",
  gender: "",
  department: "",
  phone: "",
  email: "",
  next_of_kin: "",
  next_of_kin_phone: "",
  next_of_kin_address: "",
  next_of_kin_email: "",
  next_of_kin_relationship: "",
  status: "financial",
  loan_restricted: false,
  restriction_reason: "",
};

export function useMembersPage(authLoading: boolean, logout: () => void) {
  const [members, setMembers] = useState<Member[]>([]);
  const [total, setTotal] = useState(0);
  const [skip, setSkip] = useState(0);

  // Free-text search only fires on Enter/the Search button (not per
  // keystroke), which avoids the request-race problem by construction.
  const [search, setSearch] = useState("");

  // Structured filters narrow the member GROUP shown. Independent of
  // search and of each other; each fires its own request immediately.
  const [bankFilter, setBankFilter] = useState("");
  const [departmentFilter, setDepartmentFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState<MemberStatus | "">("");
  const [filterOptions, setFilterOptions] = useState<MemberFilterOptions>({
    banks: [],
    departments: [],
  });

  const [form, setForm] = useState<MemberInput>(EMPTY_FORM);
  const [editingId, setEditingId] = useState<string | null>(null);
  // True while editing a member whose contribution is already on file: the
  // form then omits monthly_contribution_amount, because the backend refuses
  // a direct edit (409) or clear (422) -- later changes go through the
  // contribution change request flow instead.
  const [editingContributionLocked, setEditingContributionLocked] = useState(false);

  // `nokIsMember === null` is the "not yet answered" state -- used only
  // while adding a NEW member, so the required Yes/No question can't be
  // silently defaulted. Editing initializes it from the member's current
  // next_of_kin_is_member (which may itself be null for a legacy record).
  const [nokIsMember, setNokIsMember] = useState<boolean | null>(null);
  const [nokQuery, setNokQuery] = useState("");
  const [nokResults, setNokResults] = useState<NokMemberOption[]>([]);
  const [nokSelectedMember, setNokSelectedMember] = useState<NokMemberOption | null>(null);

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // The members-list's own load failure is kept SEPARATE from the
  // action-oriented `error`: a failed edit/delete must not make an
  // already-loaded table render "Unable to load members."
  const [listError, setListError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const [contribRequestsLoading, setContribRequestsLoading] = useState(false);
  const [contribRequests, setContribRequests] = useState<ContributionChangeRequest[]>([]);
  // The review panel only renders once the officer queue loads successfully.
  // An officer without savings.view gets a 403 and simply doesn't see it.
  const [contribAvailable, setContribAvailable] = useState(false);

  // Request-race guard: if two requests are ever in flight, only the
  // response to the MOST RECENTLY issued request is applied to the UI.
  const requestSeqRef = useRef(0);

  async function refresh(overrides: { search?: string; skip?: number } = {}) {
    const effectiveSkip = overrides.skip !== undefined ? overrides.skip : skip;
    const effectiveSearch = overrides.search !== undefined ? overrides.search : search;
    const mySeq = ++requestSeqRef.current;
    setLoading(true);
    setListError(null);
    try {
      const result = await listMembers({
        search: effectiveSearch,
        bank_name: bankFilter || undefined,
        department: departmentFilter || undefined,
        status: statusFilter || undefined,
        skip: effectiveSkip,
        limit: PAGE_SIZE,
      });
      if (mySeq !== requestSeqRef.current) return; // superseded by a newer request
      setMembers(result.items);
      setTotal(result.total);
      setSkip(effectiveSkip);
      // A successful list reload -- from ANY source -- clears any stale
      // action error still on screen. Inside the `mySeq` guard so a late
      // response can never clear an error a newer request will supersede.
      setError(null);
    } catch (e: any) {
      if (mySeq !== requestSeqRef.current) return;
      setListError(e.message);
    } finally {
      if (mySeq === requestSeqRef.current) setLoading(false);
    }
  }

  // Any filter change resets to page 1 and refetches immediately. Search
  // is deliberately NOT a dependency (it refetches only on Enter/Search/
  // Clear) so typing doesn't trigger this effect on every keystroke.
  useEffect(() => {
    if (!authLoading) refresh({ skip: 0 });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [authLoading, bankFilter, departmentFilter, statusFilter]);

  useEffect(() => {
    if (!authLoading) {
      getMemberFilterOptions()
        .then(setFilterOptions)
        .catch(() => {
          /* Non-fatal: filter dropdowns just show as empty/"All" if this fails. */
        });
    }
  }, [authLoading]);

  useEffect(() => {
    if (!authLoading) refreshContributionRequests();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [authLoading]);

  function goToPage(newSkip: number) {
    if (newSkip < 0 || newSkip >= total) return;
    refresh({ skip: newSkip });
  }

  function clearFilters() {
    setSearch("");
    setBankFilter("");
    setDepartmentFilter("");
    setStatusFilter("");
    // The filter resets above trigger the effect's refetch at skip=0
    // already; refresh with an empty search too, in case only `search`
    // had a value (which isn't watched by that effect).
    refresh({ search: "", skip: 0 });
  }

  const activeFilterDescriptions: string[] = [];
  if (bankFilter) activeFilterDescriptions.push(`Bank: ${bankFilter}`);
  if (departmentFilter) activeFilterDescriptions.push(`Department: ${departmentFilter}`);
  if (statusFilter) activeFilterDescriptions.push(`Status: ${statusFilter === "financial" ? "Financial" : "Non-financial"}`);
  const hasActiveFilters = Boolean(search || bankFilter || departmentFilter || statusFilter);

  function setField<K extends keyof MemberInput>(key: K, value: MemberInput[K]) {
    setForm((current) => ({ ...current, [key]: value }) as MemberInput);
  }

  function startEdit(m: Member) {
    setEditingId(m.id);
    setForm({
      psn: m.psn,
      name: m.name,
      bank_name: m.bank_name || "",
      account_number: m.account_number || "",
      gender: m.gender || "",
      department: m.department || "",
      phone: m.phone || "",
      email: m.email || "",
      next_of_kin: m.next_of_kin || "",
      next_of_kin_phone: m.next_of_kin_phone || "",
      next_of_kin_address: m.next_of_kin_address || "",
      next_of_kin_email: m.next_of_kin_email || "",
      next_of_kin_relationship: m.next_of_kin_relationship || "",
      status: m.status,
      loan_restricted: m.loan_restricted,
      restriction_reason: m.restriction_reason || "",
      monthly_contribution_amount: m.monthly_contribution_amount
        ? parseFloat(m.monthly_contribution_amount)
        : undefined,
    });
    setEditingContributionLocked(m.monthly_contribution_amount != null);
    setNokIsMember(m.next_of_kin_is_member ?? null);
    setNokSelectedMember(m.next_of_kin_member ?? null);
    setNokQuery("");
    setNokResults([]);
  }

  function resetForm() {
    setEditingId(null);
    setEditingContributionLocked(false);
    setForm(EMPTY_FORM);
    setNokIsMember(null);
    setNokSelectedMember(null);
    setNokQuery("");
    setNokResults([]);
  }

  function chooseNokIsMember(value: boolean) {
    setNokIsMember(value);
    if (!value) {
      setNokSelectedMember(null);
      setNokQuery("");
      setNokResults([]);
    }
  }

  function selectNokMember(m: NokMemberOption) {
    setNokSelectedMember(m);
    setNokResults([]);
    setNokQuery("");
  }

  async function searchNokMembers() {
    if (!nokQuery.trim()) {
      setNokResults([]);
      return;
    }
    try {
      const result = await listMembers({ search: nokQuery, limit: 10 });
      // A member can't be their own Next of Kin (backend enforces this
      // with a 409 either way), so filtering it out means the person
      // editing never sees a choice the backend would just reject.
      setNokResults(editingId ? result.items.filter((m) => m.id !== editingId) : result.items);
    } catch {
      // A failed suggestion search shouldn't blow away the top-level
      // `error` state -- just show no results.
      setNokResults([]);
    }
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);

    // Adding a new member requires an explicit Yes/No answer -- an
    // unanswered (null) state is caught here with a clear message rather
    // than falling through to the backend's 422.
    if (!editingId && nokIsMember === null) {
      setError("Please answer whether this member's Next of Kin is also a cooperative member.");
      return;
    }
    if (nokIsMember === true && !nokSelectedMember) {
      setError("Please search for and select the Next-of-Kin member.");
      return;
    }

    // On edit, only send the Next-of-Kin fields when this session's
    // editing actually touched them -- otherwise they are omitted
    // (undefined, dropped by JSON.stringify) so the existing
    // relationship is left alone.
    const payload: MemberInput = {
      ...form,
      ...(nokIsMember !== null
        ? {
            next_of_kin_is_member: nokIsMember,
            next_of_kin_member_id: nokIsMember ? nokSelectedMember?.id : undefined,
          }
        : {}),
    };

    // Contribution is bootstrap-only through this form. Once it is on file
    // (editingContributionLocked) the backend refuses a direct edit (409),
    // and a blank value must never go over the wire as null (422). Only send
    // a real number being recorded for a member who has none yet.
    if (editingContributionLocked || typeof payload.monthly_contribution_amount !== "number") {
      delete payload.monthly_contribution_amount;
    }

    try {
      if (editingId) {
        await updateMember(editingId, payload);
      } else {
        await createMember(payload);
      }
      resetForm();
      await refresh();
    } catch (e: any) {
      setError(describeError(e));
    }
  }

  async function handleDelete(id: string) {
    if (!confirm("Delete this member?")) return;
    setError(null);
    try {
      await deleteMember(id);
      await refresh();
    } catch (e: any) {
      setError(describeError(e));
    }
  }

  async function handleCreateLogin(member: Member) {
    const temp = prompt(
      `Set a temporary password for ${member.name} (PSN ${member.psn}). They'll be forced to change it on first login.`
    );
    if (!temp) return;
    setError(null);
    setSuccess(null);
    try {
      await createMemberLogin(member.id, temp);
      setSuccess(`Login created for ${member.name}. Share the PSN and temporary password with them.`);
      await refresh();
    } catch (e: any) {
      setError(describeError(e));
    }
  }

  // These call the same authoritative backend endpoint that deactivates
  // or reactivates an EXISTING login -- never creates a new one. Which of
  // Create/Deactivate/Reactivate renders for a row is decided entirely by
  // member.login_account_status, not by any frontend-side assumption.
  async function handleDeactivateLogin(member: Member) {
    if (!confirm(`Deactivate ${member.name}'s login? They will be signed out and unable to log in until reactivated.`)) return;
    setError(null);
    setSuccess(null);
    try {
      await updateMemberLoginStatus(member.id, "deactivated");
      setSuccess(`Login deactivated for ${member.name}.`);
      await refresh();
    } catch (e: any) {
      setError(describeError(e));
    }
  }

  async function handleReactivateLogin(member: Member) {
    setError(null);
    setSuccess(null);
    try {
      await updateMemberLoginStatus(member.id, "active");
      setSuccess(`Login reactivated for ${member.name}.`);
      await refresh();
    } catch (e: any) {
      setError(describeError(e));
    }
  }

  // Recording an exit is not the same as flipping status to
  // non_financial in the edit form: only this endpoint sets the exit
  // date, which is what tells a withdrawn member apart from one who
  // simply fell behind. The backend stops short of moving money, so the
  // savings offset still has to be posted on the repayment flow.
  async function handleWithdraw(member: Member) {
    const reason = prompt(
      `Record that ${member.name} (PSN ${member.psn}) has left the cooperative.\n\n` +
        "Why have they exited? This is kept on their record and in the audit trail."
    );
    if (!reason || !reason.trim()) return;
    setError(null);
    setSuccess(null);
    try {
      const result = await withdrawMember(member.id, reason.trim());
      const outstanding = Number(result.active_loan_outstanding);
      setSuccess(
        outstanding > 0
          ? `${member.name} exited. Savings ${result.savings_balance} against ${result.active_loan_count} ` +
              `outstanding loan(s) totalling ${result.active_loan_outstanding} -- ` +
              `${result.payroll_recovery_still_due} still to recover from payroll.`
          : `${member.name} exited. Savings balance ${result.savings_balance}, no loans outstanding.`
      );
      await refresh();
    } catch (e: any) {
      setError(describeError(e));
    }
  }

  function changeSearch(value: string) {
    setSearch(value);
    if (value === "") {
      // Clearing via backspace/delete refreshes immediately too. Pass
      // the empty string directly rather than relying on `search` state,
      // which hasn't re-rendered with the new value yet.
      refresh({ search: "", skip: 0 });
    }
  }

  function clearSearch() {
    setSearch("");
    refresh({ search: "", skip: 0 });
  }

  async function refreshContributionRequests() {
    setContribRequestsLoading(true);
    try {
      const data = await listContributionChangeRequests();
      setContribRequests(data);
      setContribAvailable(true);
    } catch {
      // Non-fatal: an officer without savings.view (or a network blip) just
      // doesn't get the review panel. Action errors below are still surfaced.
      setContribAvailable(false);
    } finally {
      setContribRequestsLoading(false);
    }
  }

  async function approveContribution(id: string, reason: string) {
    setError(null);
    setSuccess(null);
    try {
      await approveContributionChangeRequest(id, { reason: reason.trim() || undefined });
      setSuccess("Contribution change approved. The new amount applies from next month.");
      await refreshContributionRequests();
      await refresh();
    } catch (e: any) {
      setError(describeError(e));
    }
  }

  async function rejectContribution(id: string, reason: string) {
    setError(null);
    setSuccess(null);
    try {
      await rejectContributionChangeRequest(id, { reason: reason.trim() });
      setSuccess("Contribution change rejected.");
      await refreshContributionRequests();
    } catch (e: any) {
      setError(describeError(e));
    }
  }

  return {
    auth: { logout },
    feedback: { error, success },
    search: {
      value: search,
      onChange: changeSearch,
      onSearch: () => refresh({ skip: 0 }),
      onClear: clearSearch,
    },
    filters: {
      bank: bankFilter,
      department: departmentFilter,
      status: statusFilter,
      options: filterOptions,
      hasActive: hasActiveFilters,
      descriptions: activeFilterDescriptions,
      onBankChange: setBankFilter,
      onDepartmentChange: setDepartmentFilter,
      onStatusChange: setStatusFilter,
      onClear: clearFilters,
    },
    form: {
      values: form,
      editingId,
      contributionLocked: editingContributionLocked,
      setField,
      submit: handleSubmit,
      reset: resetForm,
      startEdit,
      nok: {
        isMember: nokIsMember,
        selected: nokSelectedMember,
        query: nokQuery,
        results: nokResults,
        chooseIsMember: chooseNokIsMember,
        setQuery: setNokQuery,
        search: searchNokMembers,
        select: selectNokMember,
        clearSelected: () => setNokSelectedMember(null),
      },
    },
    table: {
      members,
      loading,
      listError,
      skip,
      total,
      limit: PAGE_SIZE,
      onPageChange: goToPage,
      onEdit: startEdit,
      onDelete: handleDelete,
      onCreateLogin: handleCreateLogin,
      onDeactivateLogin: handleDeactivateLogin,
      onReactivateLogin: handleReactivateLogin,
      onWithdraw: handleWithdraw,
    },
    contributions: {
      requests: contribRequests,
      loading: contribRequestsLoading,
      available: contribAvailable,
      refresh: refreshContributionRequests,
      approve: approveContribution,
      reject: rejectContribution,
    },
  };
}

export type MembersPageModel = ReturnType<typeof useMembersPage>;
