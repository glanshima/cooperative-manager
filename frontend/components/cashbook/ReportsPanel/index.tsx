import { useEffect, useState } from "react";

import { formatMoney } from "@/components/deductions/labels";
import Table from "@/components/ui/Table";
import {
  CashbookAccountLedger,
  CashbookBalanceSheet,
  CashbookIncomeStatement,
  CashbookRegister,
  CashbookTrialBalance,
  getCashbookAccountLedger,
  getCashbookBalanceSheet,
  getCashbookCashRegister,
  getCashbookIncomeStatement,
  getCashbookTrialBalance,
} from "@/lib/api";
import { hasAnyPermission, REPORT_PERMISSIONS } from "@/lib/permissions";

import { monthStartIso, todayIso } from "../labels";
import type { CashbookPageModel } from "../hooks/useCashbookPage";

type ReportKind = "trial" | "income" | "balance" | "register" | "ledger";

const REPORT_LABELS: Record<ReportKind, string> = {
  trial: "Trial balance",
  income: "Income & expenditure",
  balance: "Balance sheet",
  register: "Cash register",
  ledger: "Account ledger",
};

export default function ReportsPanel({
  model,
}: {
  model: CashbookPageModel;
}) {
  const { accounts } = model;
  const canReport = hasAnyPermission(model.permissionCodes, REPORT_PERMISSIONS);

  const [kind, setKind] = useState<ReportKind>("trial");
  const [start, setStart] = useState(monthStartIso());
  const [end, setEnd] = useState(todayIso());
  const [asOf, setAsOf] = useState(todayIso());
  const [accountId, setAccountId] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [trial, setTrial] = useState<CashbookTrialBalance | null>(null);
  const [income, setIncome] = useState<CashbookIncomeStatement | null>(null);
  const [balance, setBalance] = useState<CashbookBalanceSheet | null>(null);
  const [register, setRegister] = useState<CashbookRegister | null>(null);
  const [ledger, setLedger] = useState<CashbookAccountLedger | null>(null);

  useEffect(() => {
    if (!accounts.length) return;
    if (!accountId) setAccountId(accounts[0].id);
  }, [accounts, accountId]);

  useEffect(() => {
    if (!canReport) return;
    let cancelled = false;
    setLoading(true);
    setError(null);

    async function load() {
      try {
        if (kind === "trial") {
          const data = await getCashbookTrialBalance(asOf || undefined);
          if (!cancelled) setTrial(data);
        } else if (kind === "income") {
          const data = await getCashbookIncomeStatement(start || undefined, end || undefined);
          if (!cancelled) setIncome(data);
        } else if (kind === "balance") {
          const data = await getCashbookBalanceSheet(asOf || undefined);
          if (!cancelled) setBalance(data);
        } else if (kind === "register") {
          const data = await getCashbookCashRegister(start || undefined, end || undefined);
          if (!cancelled) setRegister(data);
        } else if (kind === "ledger") {
          if (!accountId) return;
          const data = await getCashbookAccountLedger(accountId, {
            start: start || undefined,
            end: end || undefined,
          });
          if (!cancelled) setLedger(data);
        }
      } catch (e: any) {
        if (!cancelled) setError(e.message);
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    void load();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [canReport, kind, start, end, asOf, accountId]);

  if (!canReport) {
    return (
      <p style={{ color: "var(--text-muted)", fontSize: 14 }}>
        The financial statements need the report.financial or report.accounting permission. The
        journal and account balances are still available on the other tabs.
      </p>
    );
  }

  return (
    <>
      <div role="tablist" aria-label="Financial report" style={{ display: "flex", gap: 8, marginBottom: 12, flexWrap: "wrap" }}>
        {(Object.keys(REPORT_LABELS) as ReportKind[]).map((value) => (
          <button
            key={value}
            role="tab"
            aria-selected={kind === value}
            onClick={() => setKind(value)}
            style={{ fontWeight: kind === value ? 700 : 400 }}
          >
            {REPORT_LABELS[value]}
          </button>
        ))}
      </div>

      <div className="toolbar" style={{ marginBottom: 12 }}>
        {kind === "ledger" && (
          <label style={{ fontSize: 13, color: "var(--text-muted)" }}>
            Account
            <select
              aria-label="Ledger account"
              value={accountId}
              onChange={(e) => setAccountId(e.target.value)}
            >
              {accounts.map((account) => (
                <option key={account.id} value={account.id}>
                  {account.code} — {account.name}
                </option>
              ))}
            </select>
          </label>
        )}
        {kind === "trial" || kind === "balance" ? (
          <label style={{ fontSize: 13, color: "var(--text-muted)" }}>
            As of
            <input
              type="date"
              aria-label="Report date"
              value={asOf}
              onChange={(e) => setAsOf(e.target.value)}
            />
          </label>
        ) : (
          <>
            <label style={{ fontSize: 13, color: "var(--text-muted)" }}>
              From
              <input
                type="date"
                aria-label="Report from"
                value={start}
                onChange={(e) => setStart(e.target.value)}
              />
            </label>
            <label style={{ fontSize: 13, color: "var(--text-muted)" }}>
              To
              <input
                type="date"
                aria-label="Report to"
                value={end}
                onChange={(e) => setEnd(e.target.value)}
              />
            </label>
          </>
        )}
      </div>

      {loading && <p>Loading report…</p>}
      {error && <p style={{ color: "crimson", fontWeight: 600 }}>Error: {error}</p>}

      {!loading && !error && kind === "trial" && trial && (
        <Table>
          <thead>
            <tr>
              <th>Code</th>
              <th>Account</th>
              <th>Debit</th>
              <th>Credit</th>
            </tr>
          </thead>
          <tbody>
            {trial.rows.map((row) => (
              <tr key={row.account_id}>
                <td>{row.code}</td>
                <td>{row.name}</td>
                <td>{Number(row.debit) === 0 ? "—" : `₦${formatMoney(row.debit)}`}</td>
                <td>{Number(row.credit) === 0 ? "—" : `₦${formatMoney(row.credit)}`}</td>
              </tr>
            ))}
            {trial.rows.length === 0 && (
              <tr>
                <td colSpan={4}>Nothing posted yet.</td>
              </tr>
            )}
          </tbody>
        </Table>
      )}

      {!loading && !error && kind === "trial" && trial && (
        <p style={{ fontSize: 13 }}>
          Totals — debits ₦{formatMoney(trial.total_debit)}, credits ₦{formatMoney(trial.total_credit)}{" "}
          {trial.balanced ? (
            <span className="badge badge--success">Balanced</span>
          ) : (
            <span className="badge badge--danger">Out of balance</span>
          )}
        </p>
      )}

      {!loading && !error && kind === "income" && income && (
        <>
          <Table>
            <thead>
              <tr>
                <th>Income</th>
                <th>Amount</th>
              </tr>
            </thead>
            <tbody>
              {income.income.map((row) => (
                <tr key={row.account_id}>
                  <td>
                    {row.code} {row.name}
                  </td>
                  <td>₦{formatMoney(row.amount)}</td>
                </tr>
              ))}
              <tr>
                <td>
                  <strong>Total income</strong>
                </td>
                <td>
                  <strong>₦{formatMoney(income.total_income)}</strong>
                </td>
              </tr>
            </tbody>
          </Table>
          <div style={{ height: 12 }} />
          <Table>
            <thead>
              <tr>
                <th>Expenditure</th>
                <th>Amount</th>
              </tr>
            </thead>
            <tbody>
              {income.expenses.map((row) => (
                <tr key={row.account_id}>
                  <td>
                    {row.code} {row.name}
                  </td>
                  <td>₦{formatMoney(row.amount)}</td>
                </tr>
              ))}
              {income.expenses.length === 0 && (
                <tr>
                  <td colSpan={2}>No expenditure recorded for this period.</td>
                </tr>
              )}
              <tr>
                <td>
                  <strong>Total expenditure</strong>
                </td>
                <td>
                  <strong>₦{formatMoney(income.total_expenses)}</strong>
                </td>
              </tr>
            </tbody>
          </Table>
          <p style={{ fontSize: 14 }}>
            <strong>Surplus for the period:</strong> ₦{formatMoney(income.surplus)}
          </p>
        </>
      )}

      {!loading && !error && kind === "balance" && balance && (
        <>
          <MovementTable title="Assets" rows={balance.assets} />
          <div style={{ height: 12 }} />
          <MovementTable title="Liabilities" rows={balance.liabilities} />
          <div style={{ height: 12 }} />
          <MovementTable title="Equity" rows={balance.equity} />
          <dl className="detail-grid" style={{ marginTop: 12 }}>
            <div>
              <dt>Surplus brought forward</dt>
              <dd>₦{formatMoney(balance.surplus)}</dd>
            </div>
            <div>
              <dt>Total assets</dt>
              <dd>₦{formatMoney(balance.total_assets)}</dd>
            </div>
            <div>
              <dt>Liabilities + equity</dt>
              <dd>₦{formatMoney(Number(balance.total_liabilities) + Number(balance.total_equity))}</dd>
            </div>
            <div>
              <dt>Balance check</dt>
              <dd>
                {balance.balanced ? (
                  <span className="badge badge--success">Balances</span>
                ) : (
                  <span className="badge badge--danger">Does not balance</span>
                )}
              </dd>
            </div>
          </dl>
        </>
      )}

      {!loading && !error && kind === "register" && register && (
        <>
          <Table>
            <thead>
              <tr>
                <th>Date</th>
                <th>Narration</th>
                <th>Account</th>
                <th>Amount</th>
              </tr>
            </thead>
            <tbody>
              {register.rows.map((row, index) => (
                <tr key={`${row.entry_date}-${index}`}>
                  <td>{row.entry_date}</td>
                  <td>{row.narration}</td>
                  <td>
                    {row.account_code} {row.account_name}
                  </td>
                  <td>₦{formatMoney(row.amount)}</td>
                </tr>
              ))}
              {register.rows.length === 0 && (
                <tr>
                  <td colSpan={4}>No cash or bank movement in this period.</td>
                </tr>
              )}
            </tbody>
          </Table>
          <p style={{ fontSize: 13 }}>
            Net movement ₦{formatMoney(register.total)} · Cash ₦{formatMoney(register.cash_balance)} ·
            Bank ₦{formatMoney(register.bank_balance)}
          </p>
        </>
      )}

      {!loading && !error && kind === "ledger" && ledger && (
        <>
          <p style={{ fontSize: 13 }}>
            {ledger.account.code} {ledger.account.name} — opening ₦
            {formatMoney(ledger.opening_balance)}
          </p>
          <Table>
            <thead>
              <tr>
                <th>Date</th>
                <th>Narration</th>
                <th>Debit</th>
                <th>Credit</th>
                <th>Balance</th>
              </tr>
            </thead>
            <tbody>
              {ledger.rows.map((row, index) => (
                <tr key={index}>
                  <td>{row.entry_date}</td>
                  <td>
                    {row.narration}
                    {row.reference ? (
                      <div style={{ fontSize: 12, color: "var(--text-muted)" }}>Ref {row.reference}</div>
                    ) : null}
                  </td>
                  <td>{Number(row.debit) === 0 ? "—" : `₦${formatMoney(row.debit)}`}</td>
                  <td>{Number(row.credit) === 0 ? "—" : `₦${formatMoney(row.credit)}`}</td>
                  <td>₦{formatMoney(row.balance)}</td>
                </tr>
              ))}
              {ledger.rows.length === 0 && (
                <tr>
                  <td colSpan={5}>No movement in this period.</td>
                </tr>
              )}
            </tbody>
          </Table>
          <p style={{ fontSize: 13 }}>
            <strong>Closing balance:</strong> ₦{formatMoney(ledger.closing_balance)}
          </p>
        </>
      )}
    </>
  );
}

function MovementTable({
  title,
  rows,
}: {
  title: string;
  rows: { account_id: string; code: string; name: string; amount: string }[];
}) {
  return (
    <Table>
      <thead>
        <tr>
          <th>{title}</th>
          <th>Amount</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => (
          <tr key={row.account_id}>
            <td>
              {row.code} {row.name}
            </td>
            <td>₦{formatMoney(row.amount)}</td>
          </tr>
        ))}
        {rows.length === 0 && (
          <tr>
            <td colSpan={2}>None.</td>
          </tr>
        )}
      </tbody>
    </Table>
  );
}
