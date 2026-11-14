# Implementation Report: Cooperative Manager – Phase 1

## 1. Admin Dashboard (`/admin/dashboard`)

### Access guard

The route is protected by `useAuth({ requireAuth: true, requirePasswordChanged: true, requireRole: "admin" })`:

| Visitor | Outcome |
|---|---|
| No session token | Redirected to `/login` |
| Valid token, role ≠ `admin` | Redirected to `/` |
| Admin whose `must_change_password` is true | Redirected to `/change-password` |
| Authenticated admin, password already changed | Dashboard rendered |

### Components

`app/admin/dashboard/page.tsx` uses `useAdminDashboardPage` and `AdminDashboardView`. It does **not** call any member-scoped endpoints (`/api/members/me`, `/api/loan-applications`, `/api/loans`, `/api/loan-types`).

`useAdminDashboardPage` (`components/admin-dashboard/hooks/useAdminDashboardPage.ts`):
- Calls `GET /api/settings` once auth resolves.
- Derives `membersEnabled`, `loansEnabled`, and `deductionsEnabled` from the returned flags.
- Exposes `loading`, `settings`, `settingsError`, `modules`, and `auth`.

`AdminDashboardView` (`components/admin-dashboard/AdminDashboardView/index.tsx`):
- Renders navigation cards to every existing admin area.
- Module-gated sections (Members, Loans, Deductions) are hidden when the corresponding module is disabled.
- Core administration links (Staff / Admin users, Offices, Roles and permissions, Audit log, Settings) are always visible.

| Section | Requires module | Links |
|---|---|---|
| Members | `members` | Member records → `/members` |
| Loans | `loans` | Loan applications, Disbursements, Loan repayments |
| Deductions | `deductions` | Payroll deductions → `/admin/deductions` |
| Administration | — | Staff / Admin users, Offices, Roles and permissions, Audit log, Settings |

---

## 2. Member Dashboard (`/dashboard`)

Protected by `useAuth({ requireRole: "member" })`. Uses `useDashboardPage` and `DashboardView`, which call member-scoped endpoints:

- `GET /api/members/me` — the member's own record
- `GET /api/settings` — cooperative settings and module flags
- When the Loans module is enabled: `GET /api/loan-applications`, `GET /api/loans`, `GET /api/loan-types`

Displays: contribution balance, loan restriction status, loan application form (when eligible), open applications, and active loans with a repayment submission form.

---

## 3. Login and post-password-change redirects

### Login (`/login`)

After a successful `POST /api/auth/login`:

| Condition | Redirect |
|---|---|
| `must_change_password === true` | `/change-password` |
| `role === "admin"` | `/admin/dashboard` |
| `role === "member"` | `/dashboard` |

### Change-password (`/change-password`)

After a successful `POST /api/auth/change-password`:

| `updated.role` | Redirect |
|---|---|
| `"admin"` | `/admin/dashboard` |
| `"member"` | `/dashboard` |

---

## 4. Members management (`/members`)

Protected by `useAuth({ requireRole: "admin" })` and `ModuleGate module="members"`. Uses `MembersView` / `useMembersPage`. Provides member search and filtering, member creation, editing, deactivation/reactivation, and a contribution change review panel.

---

## 5. Other admin areas

| Route | Purpose |
|---|---|
| `/admin/users` | Create and manage admin accounts; role assignment; member-link management |
| `/admin/offices` | Create and manage offices and positions |
| `/admin/roles` | Define roles and configure permission grants |
| `/admin/audit` | Browse the system audit log |
| `/admin/settings` | Edit cooperative-wide settings and module toggles |
| `/admin/loan-applications` | Review loan applications (verify fee, approve/reject) |
| `/admin/disbursements` | Prepare, approve, submit, and reconcile disbursements |
| `/admin/loan-repayments` | Verify member-submitted repayments |
| `/admin/deductions` | Monthly payroll deduction worklist (create, submit, confirm) |

---

## 6. Arrears line

`loan_arrears` is a supported deduction-line category in `PayrollDeductionLine`. Lines of this category carry a `months_behind` property used by the deductions worklist UI to annotate overdue repayment entries.

---

## 7. Build and test results (2026-11-14)

All commands were run locally; the backend suite ran against the offline sandbox Postgres (`127.0.0.1:55432`, database `mact_test`), never production.

| Check | Command | Result |
|---|---|---|
| Backend tests | `pytest` in `backend/` with `DATABASE_URL` → `mact_test` | **296 passed**, 0 failed |
| Frontend tests | `npx vitest run` in `frontend/` | **21 files / 132 tests passed**, 0 failed |
| Type check | `npx tsc --noEmit` | clean (exit 0) |
| Production build | `npm run build` | compiled successfully; TypeScript finished with no errors; 20/20 static pages generated |

Next.js prints a deprecation notice for React 18 (Next 16 still supports it); the build is not affected.

---

## 8. Payroll deductions work order (2026-11-14)

### 8.1 Draft creation failing after a void — root cause and fix

**Root cause.** `loan_arrears` is a native Postgres enum value plus a check constraint on `payroll_deduction_lines`. The production database has **not** had `scripts/manual_migration_2026_11_loan_arrears_lines.sql` applied, so a replacement draft that carries an arrears line is rejected by the database. That unhandled error becomes a 500 from the serverless function; Vercel's error response carries no CORS headers, so the browser surfaces it as `TypeError: Failed to fetch`. The transaction rolls back, so the draft was **not** committed despite the client showing no response.

**Fixes (implemented and verified):**

- `backend/app/models.py` — the `ck_payroll_deduction_lines_loan_link` check constraint now names the two categories that must **not** carry a loan (`monthly_contribution`, `other`) instead of listing only `loan_repayment`, so `loan_arrears` lines are valid when the schema is created from the models.
- `frontend/lib/api/client.ts` — `fetch` rejection is caught and reported as an `ApiError` with `transport: true` and an actionable message (check connection, reload before retrying so a retry cannot duplicate an entry). Server-provided validation/permission messages are unchanged.
- `frontend/components/deductions/hooks/useDeductionsPage.ts` — `saveDraft` no longer treats a failed post-save refresh as a failed save, and when a create fails at the transport layer it looks the member/month up in the ledger first. If the draft is already there, it reports "Draft saved…" and refreshes both lists instead of inviting a duplicate retry.
- After a void the officer is returned to the ledger and can re-enter the member from the **Entered/Pending** worklist; a replacement arrears draft saves and appears in **Entered**.

**Tests:** `test_a_replacement_arrears_draft_can_follow_a_void` (backend); `sends a replacement arrears draft after the previous entry was voided`, `reports an unreachable server without claiming the draft was lost`, `treats a draft found in the ledger as saved when the reply never arrives`, `replaces a rejected fetch with an actionable transport message` (frontend).

**Deployment action — completed 2026-11-14.** The production database was missing the enum value and still carried the old constraint, so `scripts/manual_migration_2026_11_loan_arrears_lines.sql` was applied directly to the production Neon database (branch `production`) in a single committed transaction. Verified afterwards: the `payrolldeductionlinecategory` enum now includes `loan_arrears`, the `ck_payroll_deduction_lines_loan_link` constraint has the corrected positive form, and the existing 20 deduction lines are untouched. The connection string was never printed.

### 8.2 Accessible server-side search

- `GET /api/payroll-deductions` accepts `search` (max 100 chars) and filters on member name, member PSN, payroll reference and note. `GET /api/payroll-deductions/worklist` accepts `search` and filters on member name and PSN. Both use case-insensitive matching with `%` / `_` / `\` escaped, so a typed wildcard is literal.
- Search is applied before pagination, so it reaches records outside the loaded page; `total` is the filtered count.
- Worklist month-wide counts (`due_count`, `pending_count`, `entered_count`, `expected_total`) stay month-wide; only the rows and page total narrow. The ledger month totals stay schedule-derived and month-wide.
- UI: labelled search fields (worklist "Search due members by name or PSN"; ledger "Search ledger by name, PSN, payroll reference or note"), a labelled Clear search action, a `role="status"` line announcing the filtered count and stating which figures are month-wide, and search-aware empty states. Month/status/segment filters are preserved while searching and page size changes keep the active term.
- `frontend/lib/api/deductions.ts` carries the new parameter for both endpoints.

**Tests:** backend `test_ledger_search_finds_a_member_across_pages_by_psn_name_reference_and_note` (across pagination, combined with status, literal `%`), `test_worklist_search_narrows_rows_but_keeps_the_month_wide_counts`; frontend worklist (labelled field, clear, filtered announcement, empty result), ledger filters (new `DeductionFilters/index.test.tsx`), ledger table empty state.

### 8.3 The "0.3" amount change

**Evidence.** A read-only audit of production deduction lines found **no** amount that differs from the server's expected amount (20 lines, 0 mismatches) and no 0.30 anywhere in live data. The three production loans have 18/24/30-month tenures, where instalment rounding drift is at most 0.15. No fixed adjustment, percentage conversion or rounding step in the payroll path adds or subtracts 0.30.

**Where 0.30 can legitimately come from.** The loan model is interest-at-source: `total_repayable = principal + flat_charge`, `monthly_installment = total_repayable / tenure` stored as `Numeric(14,2)`. At long tenures the rounded instalment can overshoot the total. Concrete case: principal 100,000.50 over 60 months → stored instalment 1,666.68; 60 × 1,666.68 = 100,000.80, i.e. **0.30 more** than the total. The expectation engine caps the final instalment at the remaining balance (1,666.38) and does not emit a spurious arrears line for the over-rounding.

**Defects found and fixed while tracing it:**

- The admin disburse preview added interest to "Total repayable" even though the backend deducts interest at source. `computeDisbursePreview` in `frontend/components/loans/hooks/useLoansPage.ts` now mirrors `loan_calc.compute_loan_terms` (only the flat charge is added; net paid-out is shown) and the form labels the interest as deducted at source.
- Editing a draft silently dropped its existing `loan_arrears` line, because the form only offered a catch-up row when the officer added one. The form now starts with the arrears line already on the draft.

**Test:** `test_a_sixty_month_instalment_that_rounds_to_0_30_more_is_absorbed_by_the_last_payment` (asserts the 0.30 overshoot in the stored instalment and the final 1,666.38 instalment); `useLoansPage.test.ts` for the preview; `keeps an existing arrears line when editing a draft`.

### 8.4 Deduction form as an accessible modal

`frontend/components/deductions/DeductionForm/index.tsx` now renders a modal for Enter, Add any member, New deduction and Edit draft:

- `role="dialog"`, `aria-modal="true"`, `aria-labelledby` pointing at the heading; visible close button top-right ("Close deduction form").
- Closes on Escape and on a backdrop click; clicks inside the dialog do not close it. While a save is busy, Escape, backdrop clicks and the close button are inert.
- Focus moves to the first sensible control on open (member picker for blank entry, contribution for queue/edit entry) and returns to the opener on close; Tab is contained within the dialog.
- The discard notice "Closing this form discards anything you have not saved." is shown in every mode.
- Saving, conflict locking, validation messages and busy states behave as before; validation errors keep the dialog open.

**Tests:** 7 modal tests (semantics, close button, Escape, backdrop vs inside click, initial focus/restore, busy guard, validation stays open) plus the editing test above.

No code was pushed or merged, and no application deploy was performed. The only production change was the arrears schema migration recorded in §8.1.
