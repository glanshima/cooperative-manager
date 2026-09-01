"use client";

import { useEffect, useRef, useState } from "react";
import { useAuth } from "../../lib/useAuth";
import {
  Member,
  MemberInput,
  MemberFilterOptions,
  MemberStatus,
  ApiError,
  listMembers,
  getMemberFilterOptions,
  createMember,
  updateMember,
  deleteMember,
  createMemberLogin,
  updateMemberLoginStatus,
} from "../../lib/api";

/** Minimal shape for the Next-of-Kin member picker -- same fields as
 * Member.next_of_kin_member (schemas.py's NextOfKinMemberSummary), plus
 * whatever listMembers/search already returns (a full Member, but only
 * these fields are used here). */
type NokMemberOption = { id: string; psn: string; name: string; phone?: string | null };

function describeMemberOption(m: NokMemberOption): string {
  return `${m.psn} — ${m.name}`;
}

/** Appends the eligible-approvers list to a self-conflict error message,
 * when the backend included one (self_conflict.py / require_no_self_conflict),
 * so the admin sees who else can do this instead of just a dead-end
 * denial. Falls back to the plain message for any other kind of error. */
function describeError(e: unknown): string {
  if (e instanceof ApiError && e.detail && typeof e.detail === "object") {
    const detail = e.detail as { eligible_approvers?: { username: string }[]; no_eligible_approver_available?: boolean };
    if (detail.eligible_approvers) {
      if (detail.eligible_approvers.length > 0) {
        const names = detail.eligible_approvers.map((a) => a.username).join(", ");
        return `${e.message} Eligible approvers: ${names}.`;
      }
      if (detail.no_eligible_approver_available) {
        return `${e.message} No other eligible officer currently holds this permission.`;
      }
    }
  }
  return e instanceof Error ? e.message : String(e);
}

const PAGE_SIZE = 25;

const emptyForm: MemberInput = {
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

export default function MembersPage() {
  const { loading: authLoading, logout } = useAuth({
    requireAuth: true,
    requirePasswordChanged: true,
    requireRole: "admin",
  });

  const [members, setMembers] = useState<Member[]>([]);
  const [total, setTotal] = useState(0);
  const [skip, setSkip] = useState(0);

  // Free-text search: identifies specific member(s) by Member Number/
  // PSN, name, or phone. Only fires on Enter/the Search button (not per
  // keystroke) -- same behavior as before this remediation, kept as-is
  // per the instruction not to add complexity where the existing
  // approach already avoids the request-race problem by construction
  // (it simply doesn't fire a request per keystroke).
  const [search, setSearch] = useState("");

  // Structured filters: narrow the member GROUP shown. Independent of
  // search, independent of each other, and each fires its own request
  // immediately on change (Members Search & Filtering Remediation,
  // Section 1) -- the administrator never has to type anything into
  // search to use these.
  const [bankFilter, setBankFilter] = useState("");
  const [departmentFilter, setDepartmentFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState<MemberStatus | "">("");
  const [filterOptions, setFilterOptions] = useState<MemberFilterOptions>({
    banks: [],
    departments: [],
  });

  const [form, setForm] = useState<MemberInput>(emptyForm);
  const [editingId, setEditingId] = useState<string | null>(null);

  // Member Relationship / Next-of-Kin Controlled Remediation (2026-09):
  // separate state from `form` above, mirroring the admin/users page's
  // existing member-search-and-select pattern (searchMembersFor there)
  // rather than inventing a new one. `nokIsMember === null` is the
  // "not yet answered" state -- used only while adding a NEW member, so
  // the required Yes/No question (Section 1) can't be silently
  // defaulted; editing an existing member initializes this from that
  // member's current next_of_kin_is_member (which itself may be null
  // for a legacy record -- see lib/api.ts's Member.next_of_kin_is_member
  // doc comment).
  const [nokIsMember, setNokIsMember] = useState<boolean | null>(null);
  const [nokQuery, setNokQuery] = useState("");
  const [nokResults, setNokResults] = useState<NokMemberOption[]>([]);
  const [nokSelectedMember, setNokSelectedMember] = useState<NokMemberOption | null>(null);

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Members-list-table's own load failure -- kept SEPARATE from the
  // action-oriented `error` above. Bug fixed 2026-08-30: these two were
  // previously the same state, so a self-conflict 409 (or any other
  // failure) from Edit/Delete/Create-login/etc. would also make the
  // ALREADY-successfully-loaded members table incorrectly render
  // "Unable to load members." -- conflating "this one action failed"
  // with "the list itself failed to load" even when the list was fine.
  const [listError, setListError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  // Request-race guard (Section 15): if two requests are ever in flight
  // (e.g. two filter changes fired close together), only the response to
  // the MOST RECENTLY issued request is ever applied to the UI.
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
      if (mySeq !== requestSeqRef.current) return; // a newer request has already superseded this one
      setMembers(result.items);
      setTotal(result.total);
      setSkip(effectiveSkip);
    } catch (e: any) {
      if (mySeq !== requestSeqRef.current) return;
      setListError(e.message);
    } finally {
      if (mySeq === requestSeqRef.current) setLoading(false);
    }
  }

  // Any filter change: reset to page 1 (skip=0) and refetch immediately
  // -- Section 7's mandatory pagination-reset behavior. Search is
  // deliberately NOT a dependency here (it only refetches on
  // Enter/Search/Clear, handled explicitly below) so that typing doesn't
  // trigger this effect on every keystroke.
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

  function goToPage(newSkip: number) {
    if (newSkip < 0 || newSkip >= total) return;
    refresh({ skip: newSkip });
  }

  function clearFilters() {
    setSearch("");
    setBankFilter("");
    setDepartmentFilter("");
    setStatusFilter("");
    // bank/department/status resets above trigger the useEffect's
    // refetch at skip=0 already; explicitly refresh with an empty search
    // too, in case only `search` had a value (which isn't watched by
    // that effect).
    refresh({ search: "", skip: 0 });
  }

  const activeFilterDescriptions: string[] = [];
  if (bankFilter) activeFilterDescriptions.push(`Bank: ${bankFilter}`);
  if (departmentFilter) activeFilterDescriptions.push(`Department: ${departmentFilter}`);
  if (statusFilter) activeFilterDescriptions.push(`Status: ${statusFilter === "financial" ? "Financial" : "Non-financial"}`);
  const hasActiveFilters = search || bankFilter || departmentFilter || statusFilter;

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
    });
    setNokIsMember(m.next_of_kin_is_member ?? null);
    setNokSelectedMember(m.next_of_kin_member ?? null);
    setNokQuery("");
    setNokResults([]);
  }

  function resetForm() {
    setEditingId(null);
    setForm(emptyForm);
    setNokIsMember(null);
    setNokSelectedMember(null);
    setNokQuery("");
    setNokResults([]);
  }

  async function searchNokMembers() {
    if (!nokQuery.trim()) {
      setNokResults([]);
      return;
    }
    try {
      const result = await listMembers({ search: nokQuery, limit: 10 });
      // A member can't be their own Next of Kin (backend enforces this
      // with a 409 either way -- see self_reference in
      // member_relationships.py -- but filtering it out of the search
      // results here means the person editing never sees a choice the
      // backend would just reject).
      setNokResults(editingId ? result.items.filter((m) => m.id !== editingId) : result.items);
    } catch {
      // A failed search suggestion shouldn't blow away the top-level
      // `error` state -- just show no results.
      setNokResults([]);
    }
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);

    // Member Relationship / Next-of-Kin Controlled Remediation, Section
    // 1: adding a new member requires an explicit Yes/No answer -- an
    // unanswered (null) state is caught here with a clear message
    // rather than letting it fall through to the backend's 422 (which
    // has no field context to show next to).
    if (!editingId && nokIsMember === null) {
      setError("Please answer whether this member's Next of Kin is also a cooperative member.");
      return;
    }
    if (nokIsMember === true && !nokSelectedMember) {
      setError("Please search for and select the Next-of-Kin member.");
      return;
    }

    // On edit, only send next_of_kin_is_member/next_of_kin_member_id
    // when this session's editing actually touched them -- otherwise
    // the fields are simply omitted (undefined, dropped by
    // JSON.stringify) so the existing relationship is left alone (see
    // MemberUpdate's docstring in schemas.py). "Touched" here just
    // means the current in-memory nokIsMember state, which startEdit()
    // seeded from the member's own current value -- so re-submitting an
    // edit without changing the Next-of-Kin section at all still sends
    // the same value back, which set_relationship()/clear_relationship()
    // both treat as a no-op if unchanged.
    const payload: MemberInput = {
      ...form,
      ...(nokIsMember !== null
        ? {
            next_of_kin_is_member: nokIsMember,
            next_of_kin_member_id: nokIsMember ? nokSelectedMember?.id : undefined,
          }
        : {}),
    };

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

  // Login State Reconciliation Addendum: these two call the same
  // authoritative backend endpoint (PATCH /api/members/{id}/login-status)
  // that deactivates or reactivates an EXISTING login -- never creates a
  // new one. Which of Create/Deactivate/Reactivate renders for a given
  // row is decided entirely by member.login_account_status below, not by
  // any frontend-side assumption.
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

  if (authLoading) return <main style={{ padding: 32 }}>Loading...</main>;

  return (
    <main style={{ padding: 32, maxWidth: 1100, margin: "0 auto" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <h1>Members</h1>
        <button onClick={logout}>Log out</button>
      </div>

      {error && <p style={{ color: "crimson", fontWeight: 600 }}>Error: {error}</p>}
      {listError && <p style={{ color: "crimson", fontWeight: 600 }}>Error loading members: {listError}</p>}
      {success && <p style={{ color: "green", fontWeight: 600 }}>{success}</p>}

      <section style={{ marginBottom: 12 }}>
        <span style={{ position: "relative", display: "inline-block" }}>
          <input
            placeholder="Search by member number/PSN, name, or phone"
            value={search}
            onChange={(e) => {
              const value = e.target.value;
              setSearch(value);
              if (value === "") {
                // Clearing via backspace/delete should also refresh immediately,
                // not just clicking the explicit clear button below. Pass the
                // empty string directly rather than relying on `search` state,
                // which hasn't re-rendered with the new value yet at this point.
                refresh({ search: "", skip: 0 });
              }
            }}
            onKeyDown={(e) => e.key === "Enter" && refresh({ skip: 0 })}
            style={{ padding: 8, paddingRight: search ? 28 : 8, width: 320, marginRight: 8 }}
          />
          {search && (
            <button
              onClick={() => {
                setSearch("");
                refresh({ search: "", skip: 0 });
              }}
              aria-label="Clear search"
              style={{
                position: "absolute",
                right: 36,
                top: "50%",
                transform: "translateY(-50%)",
                border: "none",
                background: "transparent",
                cursor: "pointer",
                fontSize: 16,
                lineHeight: 1,
                padding: 4,
              }}
            >
              ×
            </button>
          )}
        </span>
        <button onClick={() => refresh({ skip: 0 })}>Search</button>
      </section>

      <section style={{ marginBottom: 12, display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap" }}>
        <label>
          Bank{" "}
          <select value={bankFilter} onChange={(e) => setBankFilter(e.target.value)}>
            <option value="">All Banks</option>
            {filterOptions.banks.map((b) => (
              <option key={b} value={b}>
                {b}
              </option>
            ))}
          </select>
        </label>
        <label>
          Department{" "}
          <select value={departmentFilter} onChange={(e) => setDepartmentFilter(e.target.value)}>
            <option value="">All Departments</option>
            {filterOptions.departments.map((d) => (
              <option key={d} value={d}>
                {d}
              </option>
            ))}
          </select>
        </label>
        <label>
          Status{" "}
          <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value as MemberStatus | "")}>
            <option value="">All Statuses</option>
            <option value="financial">Financial</option>
            <option value="non_financial">Non-financial</option>
          </select>
        </label>
        {hasActiveFilters && <button onClick={clearFilters}>Clear Filters</button>}
      </section>

      <section style={{ marginBottom: 24, color: "#555", fontSize: 14 }}>
        {loading ? (
          <span>Loading…</span>
        ) : (
          <>
            <strong>
              Showing {members.length === 0 ? 0 : skip + 1}
              {members.length > 0 ? `–${skip + members.length}` : ""} of {total} member
              {total === 1 ? "" : "s"}
            </strong>
            {activeFilterDescriptions.length > 0 && <span> ({activeFilterDescriptions.join(", ")})</span>}
          </>
        )}
      </section>

      <section
        style={{
          border: "1px solid #ddd",
          borderRadius: 8,
          padding: 16,
          marginBottom: 24,
        }}
      >
        <h2>{editingId ? "Edit member" : "Add member"}</h2>
        <form
          onSubmit={handleSubmit}
          style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}
        >
          <input
            required
            placeholder="PSN"
            value={form.psn}
            disabled={!!editingId}
            onChange={(e) => setForm({ ...form, psn: e.target.value })}
          />
          <input
            required
            placeholder="Name"
            value={form.name}
            onChange={(e) => setForm({ ...form, name: e.target.value })}
          />
          <input
            placeholder="Bank name"
            value={form.bank_name}
            onChange={(e) => setForm({ ...form, bank_name: e.target.value })}
          />
          <input
            placeholder="Account number"
            value={form.account_number}
            onChange={(e) =>
              setForm({ ...form, account_number: e.target.value })
            }
          />
          <input
            placeholder="Department"
            value={form.department}
            onChange={(e) => setForm({ ...form, department: e.target.value })}
          />
          <input
            placeholder="Phone"
            value={form.phone}
            onChange={(e) => setForm({ ...form, phone: e.target.value })}
          />
          <input
            placeholder="Email"
            value={form.email}
            onChange={(e) => setForm({ ...form, email: e.target.value })}
          />
          <select
            value={form.status}
            onChange={(e) =>
              setForm({ ...form, status: e.target.value as any })
            }
          >
            <option value="financial">Financial</option>
            <option value="non_financial">Non-financial</option>
          </select>

          <div style={{ gridColumn: "1 / -1", fontWeight: 600, marginTop: 8 }}>
            Next of kin
          </div>

          {/* Member Relationship / Next-of-Kin Controlled Remediation
              (2026-09), Section 1: this Yes/No question is required for
              a NEW member (checked in handleSubmit above); for an
              existing legacy member it may start unanswered (neither
              radio selected) if next_of_kin_is_member is null -- see
              lib/api.ts's Member type doc comment -- and stays that way
              until the person editing explicitly picks one. */}
          <div style={{ gridColumn: "1 / -1" }}>
            <label style={{ marginRight: 16 }}>
              <input
                type="radio"
                name="nokIsMember"
                checked={nokIsMember === true}
                onChange={() => setNokIsMember(true)}
              />{" "}
              Next of kin is a cooperative member
            </label>
            <label>
              <input
                type="radio"
                name="nokIsMember"
                checked={nokIsMember === false}
                onChange={() => {
                  setNokIsMember(false);
                  setNokSelectedMember(null);
                  setNokQuery("");
                  setNokResults([]);
                }}
              />{" "}
              Next of kin is not a cooperative member
            </label>
          </div>

          {nokIsMember === true && (
            <div style={{ gridColumn: "1 / -1" }}>
              {nokSelectedMember ? (
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <span>
                    Selected: <strong>{describeMemberOption(nokSelectedMember)}</strong>
                  </span>
                  <button type="button" onClick={() => setNokSelectedMember(null)}>
                    Change
                  </button>
                </div>
              ) : (
                <div>
                  <input
                    placeholder="Search member by PSN, name, or phone"
                    value={nokQuery}
                    onChange={(e) => setNokQuery(e.target.value)}
                    onKeyDown={(e) => e.key === "Enter" && (e.preventDefault(), searchNokMembers())}
                    style={{ marginRight: 8 }}
                  />
                  <button type="button" onClick={searchNokMembers}>
                    Search
                  </button>
                  {nokResults.length > 0 && (
                    <ul style={{ listStyle: "none", padding: 0, margin: "8px 0" }}>
                      {nokResults.map((m) => (
                        <li key={m.id}>
                          <button
                            type="button"
                            onClick={() => {
                              setNokSelectedMember(m);
                              setNokResults([]);
                              setNokQuery("");
                            }}
                          >
                            {describeMemberOption(m)}
                          </button>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              )}
            </div>
          )}

          {nokIsMember === false && (
            <>
              <input
                placeholder="Next of kin name"
                value={form.next_of_kin}
                onChange={(e) => setForm({ ...form, next_of_kin: e.target.value })}
              />
              <input
                placeholder="Next of kin phone"
                value={form.next_of_kin_phone}
                onChange={(e) => setForm({ ...form, next_of_kin_phone: e.target.value })}
              />
              <input
                placeholder="Next of kin address"
                value={form.next_of_kin_address}
                onChange={(e) => setForm({ ...form, next_of_kin_address: e.target.value })}
              />
              <input
                placeholder="Next of kin email"
                value={form.next_of_kin_email}
                onChange={(e) => setForm({ ...form, next_of_kin_email: e.target.value })}
              />
              <input
                placeholder="Relationship (e.g. Spouse, Sibling)"
                value={form.next_of_kin_relationship}
                onChange={(e) => setForm({ ...form, next_of_kin_relationship: e.target.value })}
              />
            </>
          )}

          <label style={{ gridColumn: "1 / -1" }}>
            <input
              type="checkbox"
              checked={form.loan_restricted}
              onChange={(e) => setForm({ ...form, loan_restricted: e.target.checked })}
            />{" "}
            Loan-restricted (flag this member as unable/limited to take new loans)
          </label>
          {form.loan_restricted && (
            <input
              placeholder="Reason for restriction"
              value={form.restriction_reason}
              onChange={(e) => setForm({ ...form, restriction_reason: e.target.value })}
              style={{ gridColumn: "1 / -1" }}
            />
          )}

          <div style={{ gridColumn: "1 / -1" }}>
            <button type="submit">
              {editingId ? "Save changes" : "Add member"}
            </button>{" "}
            {editingId && (
              <button type="button" onClick={resetForm}>
                Cancel
              </button>
            )}
          </div>
        </form>
      </section>

      <section>
        {loading ? (
          <p>Loading...</p>
        ) : listError ? (
          <p>Unable to load members.</p>
        ) : members.length === 0 ? (
          <p>No matching records found.</p>
        ) : (
          <>
            <table style={{ width: "100%", borderCollapse: "collapse" }}>
              <thead>
                <tr style={{ textAlign: "left", borderBottom: "2px solid #333" }}>
                  <th>PSN</th>
                  <th>Name</th>
                  <th>Department</th>
                  <th>Status</th>
                  <th>Restricted</th>
                  <th>Phone</th>
                  <th>Next of kin</th>
                  <th>Login</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {members.map((m) => (
                  <tr key={m.id} style={{ borderBottom: "1px solid #eee" }}>
                    <td>{m.psn}</td>
                    <td>{m.name}</td>
                    <td>{m.department}</td>
                    <td>{m.status}</td>
                    <td>{m.loan_restricted ? "⚠ yes" : ""}</td>
                    <td>{m.phone}</td>
                    <td>
                      {m.next_of_kin_is_member && m.next_of_kin_member
                        ? `${describeMemberOption(m.next_of_kin_member)} (member)`
                        : m.next_of_kin_is_member === false
                        ? m.next_of_kin || "—"
                        : "—"}
                    </td>
                    <td>{m.login_account_status ?? "no login"}</td>
                    <td>
                      <button onClick={() => startEdit(m)}>Edit</button>{" "}
                      <button onClick={() => handleDelete(m.id)}>Delete</button>{" "}
                      {/* Login State Reconciliation Addendum: the action shown
                          here is derived ENTIRELY from the backend-computed
                          m.login_account_status -- never assumed. null/undefined
                          means no login exists yet. */}
                      {!m.login_account_status && (
                        <button onClick={() => handleCreateLogin(m)}>Create login</button>
                      )}
                      {m.login_account_status === "active" && (
                        <button onClick={() => handleDeactivateLogin(m)}>Deactivate login</button>
                      )}
                      {(m.login_account_status === "deactivated" || m.login_account_status === "suspended") && (
                        <button onClick={() => handleReactivateLogin(m)}>Reactivate login</button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            <div style={{ marginTop: 12, display: "flex", gap: 8, alignItems: "center" }}>
              <button disabled={skip === 0} onClick={() => goToPage(skip - PAGE_SIZE)}>
                Previous
              </button>
              <span>
                Page {Math.floor(skip / PAGE_SIZE) + 1} of {Math.max(1, Math.ceil(total / PAGE_SIZE))}
              </span>
              <button disabled={skip + PAGE_SIZE >= total} onClick={() => goToPage(skip + PAGE_SIZE)}>
                Next
              </button>
            </div>
          </>
        )}
      </section>
    </main>
  );
}
