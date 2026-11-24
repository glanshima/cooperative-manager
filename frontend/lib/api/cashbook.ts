import { apiFetch } from "./client";

export type CashbookAccountKind = "asset" | "liability" | "equity" | "income" | "expense";

// What produced an entry. Automatic postings name their source so the same
// event can never be posted twice; only `manual`, `opening` and `reversal`
// are ever written from the screen.
export type CashbookEntrySource =
  | "manual"
  | "opening"
  | "reversal"
  | "payroll_deduction"
  | "payroll_deduction_void"
  | "loan_disbursement"
  | "loan_repayment"
  | "loan_fee"
  | "settlement"
  | "settlement_payout"
  | "year_close"
  | "dividend_declaration"
  | "dividend_payment";

export interface CashbookAccount {
  id: string;
  code: string;
  name: string;
  kind: CashbookAccountKind;
  // Set on the accounts automatic postings target. Protected from
  // deactivation because a posting rule names them.
  system_key?: string | null;
  is_active: boolean;
  description?: string | null;
}

export interface CashbookAccountBalance extends CashbookAccount {
  debit: string;
  credit: string;
  // On the account's normal side: assets and expenses debit-positive,
  // everything else credit-positive.
  balance: string;
}

export interface CashbookLine {
  id: string;
  account_id: string;
  account_code: string;
  account_name: string;
  debit: string;
  credit: string;
}

export interface CashbookEntry {
  id: string;
  entry_date: string;
  narration: string;
  reference?: string | null;
  source: CashbookEntrySource;
  source_id?: string | null;
  reverses_entry_id?: string | null;
  reversal_reason?: string | null;
  posted_by_user_id?: string | null;
  posted_at?: string | null;
  lines: CashbookLine[];
}

export interface CashbookEntryPage {
  items: CashbookEntry[];
  total: number;
  skip: number;
  limit: number;
}

export interface CashbookLineInput {
  account_id: string;
  debit: string;
  credit: string;
}

export interface CashbookEntryInput {
  entry_date: string;
  narration: string;
  reference?: string;
  lines: CashbookLineInput[];
}

export interface CashbookOpeningInput {
  as_of: string;
  note?: string;
  lines: CashbookLineInput[];
}

export interface CashbookOverview {
  enabled: boolean;
  opened: boolean;
  opening_entry_id?: string | null;
  opening_date?: string | null;
  account_count: number;
  entry_count: number;
  cash_balance: string;
  bank_balance: string;
  current_month_locked: boolean;
  locked_periods: string[];
}

export interface CashbookPeriodLock {
  period_start: string;
  locked_by_user_id?: string | null;
  locked_at?: string | null;
  note?: string | null;
}

export interface CashbookTrialBalanceRow {
  account_id: string;
  code: string;
  name: string;
  kind: CashbookAccountKind;
  debit: string;
  credit: string;
}

export interface CashbookTrialBalance {
  as_of?: string | null;
  rows: CashbookTrialBalanceRow[];
  total_debit: string;
  total_credit: string;
  balanced: boolean;
}

export interface CashbookMovementRow {
  account_id: string;
  code: string;
  name: string;
  amount: string;
}

export interface CashbookIncomeStatement {
  start?: string | null;
  end?: string | null;
  income: CashbookMovementRow[];
  expenses: CashbookMovementRow[];
  total_income: string;
  total_expenses: string;
  surplus: string;
}

export interface CashbookBalanceSheet {
  as_of?: string | null;
  assets: CashbookMovementRow[];
  liabilities: CashbookMovementRow[];
  equity: CashbookMovementRow[];
  surplus: string;
  total_assets: string;
  total_liabilities: string;
  total_equity: string;
  balanced: boolean;
}

export interface CashbookLedgerRow {
  entry_date: string;
  narration: string;
  reference?: string | null;
  debit: string;
  credit: string;
  balance: string;
}

export interface CashbookAccountLedger {
  account: CashbookAccount;
  start?: string | null;
  end?: string | null;
  opening_balance: string;
  rows: CashbookLedgerRow[];
  closing_balance: string;
}

export interface CashbookRegisterRow {
  entry_date: string;
  narration: string;
  reference?: string | null;
  account_code: string;
  account_name: string;
  amount: string;
}

export interface CashbookRegister {
  start?: string | null;
  end?: string | null;
  rows: CashbookRegisterRow[];
  total: string;
  cash_balance: string;
  bank_balance: string;
}

export interface CashbookEntryListParams {
  start?: string;
  end?: string;
  account_id?: string;
  source?: CashbookEntrySource;
  q?: string;
  skip?: number;
  limit?: number;
}

export async function getCashbookOverview(): Promise<CashbookOverview> {
  return apiFetch<CashbookOverview>("/api/cashbook/overview");
}

export async function listCashbookAccounts(asOf?: string): Promise<CashbookAccountBalance[]> {
  return apiFetch<CashbookAccountBalance[]>("/api/cashbook/accounts", {
    searchParams: { as_of: asOf },
  });
}

export async function createCashbookAccount(input: {
  code: string;
  name: string;
  kind: CashbookAccountKind;
  description?: string;
}): Promise<CashbookAccount> {
  return apiFetch<CashbookAccount>("/api/cashbook/accounts", {
    method: "POST",
    body: input,
  });
}

export async function updateCashbookAccount(
  id: string,
  input: { name?: string; description?: string | null; is_active?: boolean }
): Promise<CashbookAccount> {
  return apiFetch<CashbookAccount>(`/api/cashbook/accounts/${id}`, {
    method: "PATCH",
    body: input,
  });
}

export async function listCashbookEntries(
  params: CashbookEntryListParams = {}
): Promise<CashbookEntryPage> {
  return apiFetch<CashbookEntryPage>("/api/cashbook/entries", {
    searchParams: {
      start: params.start,
      end: params.end,
      account_id: params.account_id,
      source: params.source,
      q: params.q,
      skip: params.skip !== undefined ? String(params.skip) : undefined,
      limit: params.limit !== undefined ? String(params.limit) : undefined,
    },
  });
}

export async function postCashbookOpening(
  input: CashbookOpeningInput
): Promise<CashbookEntry> {
  return apiFetch<CashbookEntry>("/api/cashbook/opening", {
    method: "POST",
    body: input,
  });
}

export async function createCashbookEntry(input: CashbookEntryInput): Promise<CashbookEntry> {
  return apiFetch<CashbookEntry>("/api/cashbook/entries", {
    method: "POST",
    body: input,
  });
}

export async function reverseCashbookEntry(
  id: string,
  input: { reason: string; entry_date?: string }
): Promise<CashbookEntry> {
  return apiFetch<CashbookEntry>(`/api/cashbook/entries/${id}/reverse`, {
    method: "POST",
    body: { reason: input.reason, entry_date: input.entry_date ?? null },
  });
}

export async function listCashbookPeriodLocks(): Promise<CashbookPeriodLock[]> {
  return apiFetch<CashbookPeriodLock[]>("/api/cashbook/period-locks");
}

export async function lockCashbookPeriod(input: {
  period_start: string;
  note?: string;
}): Promise<CashbookPeriodLock> {
  return apiFetch<CashbookPeriodLock>("/api/cashbook/period-locks", {
    method: "POST",
    body: { period_start: input.period_start, note: input.note },
  });
}

export async function unlockCashbookPeriod(periodStart: string): Promise<void> {
  return apiFetch<void>(`/api/cashbook/period-locks/${periodStart}`, {
    method: "DELETE",
  });
}

export async function getCashbookTrialBalance(asOf?: string): Promise<CashbookTrialBalance> {
  return apiFetch<CashbookTrialBalance>("/api/cashbook/reports/trial-balance", {
    searchParams: { as_of: asOf },
  });
}

export async function getCashbookIncomeStatement(
  start?: string,
  end?: string
): Promise<CashbookIncomeStatement> {
  return apiFetch<CashbookIncomeStatement>("/api/cashbook/reports/income-expenditure", {
    searchParams: { start, end },
  });
}

export async function getCashbookBalanceSheet(asOf?: string): Promise<CashbookBalanceSheet> {
  return apiFetch<CashbookBalanceSheet>("/api/cashbook/reports/balance-sheet", {
    searchParams: { as_of: asOf },
  });
}

export async function getCashbookCashRegister(
  start?: string,
  end?: string
): Promise<CashbookRegister> {
  return apiFetch<CashbookRegister>("/api/cashbook/reports/cash-register", {
    searchParams: { start, end },
  });
}

export async function getCashbookAccountLedger(
  accountId: string,
  params: { start?: string; end?: string } = {}
): Promise<CashbookAccountLedger> {
  return apiFetch<CashbookAccountLedger>(`/api/cashbook/reports/ledger/${accountId}`, {
    searchParams: { start: params.start, end: params.end },
  });
}
