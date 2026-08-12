"use client";

import { useEffect, useState } from "react";
import { useAuth } from "../../lib/useAuth";
import {
  Member,
  MemberInput,
  listMembers,
  createMember,
  updateMember,
  deleteMember,
  createMemberLogin,
} from "../../lib/api";

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
  const [search, setSearch] = useState("");
  const [form, setForm] = useState<MemberInput>(emptyForm);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  async function refresh() {
    setLoading(true);
    setError(null);
    try {
      setMembers(await listMembers(search));
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (!authLoading) refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [authLoading]);

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
      status: m.status,
      loan_restricted: m.loan_restricted,
      restriction_reason: m.restriction_reason || "",
    });
  }

  function resetForm() {
    setEditingId(null);
    setForm(emptyForm);
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      if (editingId) {
        await updateMember(editingId, form);
      } else {
        await createMember(form);
      }
      resetForm();
      await refresh();
    } catch (e: any) {
      setError(e.message);
    }
  }

  async function handleDelete(id: string) {
    if (!confirm("Delete this member?")) return;
    try {
      await deleteMember(id);
      await refresh();
    } catch (e: any) {
      setError(e.message);
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
    } catch (e: any) {
      setError(e.message);
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
      {success && <p style={{ color: "green", fontWeight: 600 }}>{success}</p>}

      <section style={{ marginBottom: 24 }}>
        <input
          placeholder="Search by name or PSN"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && refresh()}
          style={{ padding: 8, width: 280, marginRight: 8 }}
        />
        <button onClick={refresh}>Search</button>
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
        ) : (
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr style={{ textAlign: "left", borderBottom: "2px solid #333" }}>
                <th>PSN</th>
                <th>Name</th>
                <th>Department</th>
                <th>Status</th>
                <th>Restricted</th>
                <th>Phone</th>
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
                    <button onClick={() => startEdit(m)}>Edit</button>{" "}
                    <button onClick={() => handleDelete(m.id)}>Delete</button>{" "}
                    <button onClick={() => handleCreateLogin(m)}>Create login</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </main>
  );
}
