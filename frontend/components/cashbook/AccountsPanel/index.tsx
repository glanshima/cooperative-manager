import { formatMoney } from "@/components/deductions/labels";
import Table from "@/components/ui/Table";

import { KIND_LABELS, KIND_ORDER } from "../labels";
import type { CashbookPageModel } from "../hooks/useCashbookPage";

export default function AccountsPanel({ model }: { model: CashbookPageModel }) {
  const { accounts, accountForm, permissions, busy } = model;

  function openCreate() {
    accountForm.set({
      open: true,
      editingId: null,
      code: "",
      name: "",
      kind: "expense",
      description: "",
    });
  }

  function openEdit(accountId: string) {
    const account = accounts.find((item) => item.id === accountId);
    if (!account) return;
    accountForm.set({
      open: true,
      editingId: account.id,
      code: account.code,
      name: account.name,
      kind: account.kind,
      description: account.description ?? "",
    });
  }

  return (
    <>
      <div className="toolbar" style={{ marginBottom: 12 }}>
        <p style={{ margin: 0, color: "var(--text-muted)", fontSize: 13 }}>
          Balances are shown on each account&apos;s normal side. System accounts drive automatic
          postings and cannot be deactivated.
        </p>
        {permissions.canAdjust && !accountForm.open && (
          <button type="button" onClick={openCreate}>
            Add account
          </button>
        )}
      </div>

      {accountForm.open && (
        <div className="form-grid" style={{ marginBottom: 16 }}>
          <label style={{ fontSize: 13, color: "var(--text-muted)" }}>
            Code
            <input
              aria-label="Account code"
              value={accountForm.code}
              onChange={(e) => accountForm.set({ ...accountForm, code: e.target.value })}
              disabled={busy || Boolean(accountForm.editingId)}
              placeholder="e.g. 5020"
            />
          </label>
          <label style={{ fontSize: 13, color: "var(--text-muted)" }}>
            Name
            <input
              aria-label="Account name"
              value={accountForm.name}
              onChange={(e) => accountForm.set({ ...accountForm, name: e.target.value })}
              disabled={busy}
            />
          </label>
          <label style={{ fontSize: 13, color: "var(--text-muted)" }}>
            Type
            <select
              aria-label="Account type"
              value={accountForm.kind}
              onChange={(e) =>
                accountForm.set({
                  ...accountForm,
                  kind: e.target.value as (typeof KIND_ORDER)[number],
                })
              }
              disabled={busy || Boolean(accountForm.editingId)}
            >
              {KIND_ORDER.map((kind) => (
                <option key={kind} value={kind}>
                  {KIND_LABELS[kind]}
                </option>
              ))}
            </select>
          </label>
          <label className="form-grid__full" style={{ fontSize: 13, color: "var(--text-muted)" }}>
            Description
            <input
              aria-label="Account description"
              value={accountForm.description}
              onChange={(e) => accountForm.set({ ...accountForm, description: e.target.value })}
              disabled={busy}
              placeholder="What this account records (optional)"
            />
          </label>
          <div className="form-grid__full toolbar">
            <button type="button" disabled={busy} onClick={accountForm.submit}>
              {busy ? "Saving…" : accountForm.editingId ? "Save account" : "Add account"}
            </button>
            <button
              type="button"
              disabled={busy}
              onClick={() =>
                accountForm.set({
                  open: false,
                  editingId: null,
                  code: "",
                  name: "",
                  kind: "expense",
                  description: "",
                })
              }
            >
              Cancel
            </button>
          </div>
        </div>
      )}

      <Table>
        <thead>
          <tr>
            <th>Code</th>
            <th>Account</th>
            <th>Type</th>
            <th>Balance</th>
            <th>Status</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          {accounts.map((account) => (
            <tr key={account.id} style={account.is_active ? undefined : { opacity: 0.6 }}>
              <td>{account.code}</td>
              <td>
                {account.name}
                {account.description ? (
                  <div style={{ fontSize: 12, color: "var(--text-muted)" }}>{account.description}</div>
                ) : null}
              </td>
              <td>{KIND_LABELS[account.kind]}</td>
              <td>₦{formatMoney(account.balance)}</td>
              <td>
                <span className={`badge ${account.is_active ? "badge--success" : "badge--neutral"}`}>
                  {account.is_active ? "Active" : "Inactive"}
                </span>
                {account.system_key ? (
                  <span className="badge badge--info" style={{ marginLeft: 6 }}>
                    System
                  </span>
                ) : null}
              </td>
              <td>
                {permissions.canAdjust ? (
                  <div className="toolbar" style={{ margin: 0 }}>
                    <button type="button" className="link-button" onClick={() => openEdit(account.id)}>
                      Edit
                    </button>
                    {!account.system_key && (
                      <button
                        type="button"
                        className="link-button"
                        disabled={busy}
                        onClick={() => model.setAccountActive(account, !account.is_active)}
                      >
                        {account.is_active ? "Deactivate" : "Reactivate"}
                      </button>
                    )}
                  </div>
                ) : (
                  "—"
                )}
              </td>
            </tr>
          ))}
          {accounts.length === 0 && (
            <tr>
              <td colSpan={6}>No accounts yet.</td>
            </tr>
          )}
        </tbody>
      </Table>
    </>
  );
}
