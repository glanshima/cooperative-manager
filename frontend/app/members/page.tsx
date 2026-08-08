"use client";

import { useEffect, useState } from "react";
import {
  Member,
  MemberInput,
  listMembers,
  createMember,
  updateMember,
  deleteMember,
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
};

export default function MembersPage() {
  const [members, setMembers] = useState<Member[]>([]);
  const [search, setSearch] = useState("");
  const [form, setForm] = useState<MemberInput>(emptyForm);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

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
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

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

  return (
    <main style={{ padding: 32, maxWidth: 1000, margin: "0 auto" }}>
      <h1>Members</h1>

      {error && (
        <p style={{ color: "crimson", fontWeight: 600 }}>Error: {error}</p>
      )}

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
                  <td>{m.phone}</td>
                  <td>
                    <button onClick={() => startEdit(m)}>Edit</button>{" "}
                    <button onClick={() => handleDelete(m.id)}>Delete</button>
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
