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
| Frontend tests | `npx vitest run` in `frontend/` | **27 files / 170 tests passed**, 0 failed |
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

---

## 9. Admin navigation (2026-11-14)

### 9.1 Shared shell

`frontend/components/admin-shell/AdminNav/index.tsx` renders a `<header>` containing the brand link ("MACT Admin" → `/admin/dashboard`), a mobile menu button and a `<nav id="admin-navigation" aria-label="Admin">` landmark with a `<ul>` of links. `frontend/components/admin-shell/AdminShell/index.tsx` is a thin wrapper (`<AdminNav />{children}`) so every page gets the same menu from one list.

`frontend/components/admin-shell/hooks/useAdminNav.ts` fetches `GET /api/settings` once and derives the link list. There is a single source of truth, so no page keeps its own list.

| Link | Shown when |
|---|---|
| Dashboard → `/admin/dashboard` | always |
| Members → `/members` | `members` module enabled |
| Loans → `/loans` | `loans` module enabled |
| Loan applications → `/admin/loan-applications` | `loans` module enabled |
| Disbursements → `/admin/disbursements` | `loans` module enabled |
| Loan repayments → `/admin/loan-repayments` | `loans` module enabled |
| Payroll deductions → `/admin/deductions` | `deductions` module enabled |
| Staff / Admin users → `/admin/users` | always |
| Offices → `/admin/offices` | always |
| Roles and permissions → `/admin/roles` | always |
| Audit log → `/admin/audit` | always |
| Settings → `/admin/settings` | always |

Module-gated links are omitted until settings confirm the module is on; if the settings request fails the menu keeps only the core links, so it never advertises an area the app would then refuse to open. Every link points at a route that exists.

**Permission limitation.** The API's `CurrentUser` payload carries the user's role and super-admin flag but not permission codes, so the menu cannot hide individual links per permission grant. Visibility therefore follows the admin role plus the module flags, which is what the application already exposes client-side. The destination pages keep their own permission enforcement.

### 9.2 Accessibility and responsive behaviour

- Current page: the matching link gets `aria-current="page"` and a distinct active style; matching is exact-path.
- Semantic landmark with an accessible name (`aria-label="Admin"`); descriptive link text.
- Visible `:focus-visible` outlines on the brand, the menu button and every link.
- The menu button is labelled "Open admin navigation" / "Close admin navigation" and exposes `aria-expanded` plus `aria-controls="admin-navigation"`.
- Below 900px width the list collapses behind the menu button (`.nav` hidden, shown when `data-open="true"`); above it the menu button is hidden and links wrap in a row. Escape closes the open menu and returns focus to the button; following a link also closes it.
- Member navigation and the member dashboard are untouched — no `AdminShell` was added to any member route.

### 9.3 Files changed

- Added: `frontend/components/admin-shell/AdminNav/index.tsx`, `AdminNav.module.css`, `AdminNav/index.test.tsx`, `frontend/components/admin-shell/AdminShell/index.tsx`, `frontend/components/admin-shell/hooks/useAdminNav.ts`.
- Wrapped with `AdminShell`: `app/admin/dashboard`, `app/admin/users`, `app/admin/offices`, `app/admin/roles`, `app/admin/settings`, `app/admin/audit`, `app/admin/deductions`, `app/admin/loan-applications`, `app/admin/disbursements`, `app/admin/loan-repayments`, `app/members`, `app/loans` (`page.tsx` in each).
- The auth-loading early returns are left as bare `<main>` blocks; the menu renders once auth resolves.

### 9.4 Verification

- `AdminNav/index.test.tsx` — **9 tests**: all twelve links and their hrefs; module links omitted when modules are off; `aria-current="page"` on the current page; menu button opens and closes the panel (`aria-expanded`, `aria-controls`, `data-open`); Escape closes and restores focus; a link click closes the menu; hook adds module links once settings arrive, keeps core links when all modules are off, and keeps core links when settings fail.
- Full frontend suite: **22 files / 141 tests passed**; `npx tsc --noEmit` exit 0; `npm run build` compiled successfully (TypeScript clean, 20/20 static pages, all admin routes plus `/members` and `/loans`).
- Browser check on the local build (`http://localhost:3000`, `localadmin`): the menu starts collapsed at mobile width, the labelled button expands it to all 12 links, "Dashboard" is shown active, Escape closes it and returns focus, and following "Roles and permissions" navigates to `/admin/roles`, collapses the menu and leaves `aria-current="page"` on that link (`navLinks: 12`, `menuExpanded: "false"`).

No code was pushed or merged, and no deploy was performed for this change.

---

## 10. Deduction feedback and bulk-action eligibility (2026-11-14)

### 10.1 Why "Only submitted deductions can be confirmed" appeared next to "5 of 13 deductions updated"

The ledger's **Select all** checkbox selects every non-conflicted row on the page, whatever its status. The bulk bar then sent all selected ids to the server, and the server correctly refused the rows that were not submitted (already confirmed, drafts, etc.) one by one. The client reported the successes, then printed the collected refusals as the error banner — accurate, but it read as a failure of an action the officer had no way to scope.

**Fix:**

- `frontend/components/deductions/hooks/useDeductionsPage.ts` now mirrors the backend transition guards (`submit` → draft; `confirm`/`return_to_draft` → submitted; `not_deducted` → draft or submitted; `void` → anything not already void). A bulk request filters the selected ids to the rows the action can actually reach before calling the API.
- Rows skipped this way are stated in the result, e.g. "5 of 5 deductions updated. 8 skipped — only submitted deductions can be confirmed." A selection where nothing qualifies performs no request and explains the required state instead of surfacing a server refusal.
- `frontend/components/deductions/BulkActionsBar/index.tsx` receives the per-action reachable count, labels a partially applicable action as `Confirm (5)` out of 13 selected, disables an action no selected row can reach, and gives the reason in its `title`.
- Row-level actions are unchanged: the table already offers only the transitions each row's status allows, so a single id still goes to the server as chosen (which keeps the server's precise message for stale state).

### 10.2 Feedback that never cleared

`StatusMessage` printed the banner until the next action replaced it. In the deductions page both tones now:

- clear themselves after **10 seconds** (`useDeductionsPage`, one timer per tone, cleared on change/unmount), and
- carry a labelled **Dismiss** button ("Dismiss error" / "Dismiss message") wired to `feedback.dismissError` / `feedback.dismissMessage`.

`StatusMessage` gained optional `onDismiss` / `dismissLabel` props and now exposes `role="alert"` for errors and `role="status"` for successes; other pages that pass no dismiss handler render exactly as before.

### 10.3 Tests

- `useDeductionsPage.test.ts` (+5): mixed 13-row style selection confirms only the submitted rows and reports the skip; an all-ineligible bulk selection makes no API call and explains why; manual dismissal clears both tones; the success banner clears itself after the timeout (fake timers). The existing per-record bulk report test still passes unchanged.
- New `BulkActionsBar/index.test.tsx` (3): reachable counts in the label, disabled action with its status hint, chosen action dispatched.

### 10.4 Results

- Frontend: **23 files / 148 tests passed**; `npx tsc --noEmit` exit 0; `npm run build` compiled successfully with 20/20 static pages.
- Backend (unchanged, re-run as the gate): **296 passed** against `mact_test` on the local sandbox.
- No application deploy was performed for this fix.

---

## 11. Welcome, greeting and logout confirmation (2026-11-14)

Both dashboards render a shared `DashboardHeader` (`components/ui/DashboardHeader`), and every screen with a **Log out** button renders the shared `LogoutControl` (`components/ui/LogoutControl`). That control always shows the signed-in identity above the button and asks for confirmation before ending the session.

### 11.1 Name shown

No first/last-name fields exist in the schema: a member has a single free-text `Member.name`, and an admin has only `username` (plus an optional linked `member_id`).

- `GET /api/auth/me` now returns `member_name` (`UserOut.member_name`, optional) — the stored name of the member linked to the signed-in user, looked up in the same request. Admins without a linked member get `null`.
- `lib/names.ts` turns the stored name into `Last, First`: the last whitespace-separated token is the surname, the first given name is kept, and every further given name is reduced to an initial — `Ada Ngozi Chika Obi` → `Obi, Ada N. C.`. Names that already contain a comma are returned unchanged; a single token is returned as-is.
- `userDisplayName(user)` is the single rule for the identity line: the linked member's name when there is one, otherwise the login.
- On the member dashboard the name sits above **Log out** instead of the PSN; the PSN is shown on its own line under the greeting. Admin dashboards show the linked member's name, or the admin username when none is linked.

### 11.2 Greeting

The dashboard heading opens as `Welcome, <name>` and, five seconds after mount, settles into `timeOfDayGreeting(new Date())` + name (`lib/greeting.ts`): **Good morning** 00:00–11:59, **Good afternoon** 12:00–16:59, **Good evening** 17:00–23:59. The greeting is recomputed every minute, so a page left open across a boundary changes with the clock instead of freezing. Timers are cleared on unmount. Without a name the heading falls back to the page title ("Admin Dashboard" / "My Dashboard").

The heading stays an `<h1>` for document structure but renders at body size with emphasis (16px, weight 600) rather than the browser's 32px default.

The identity line (name, or admin username) sits directly above the **Log out** button on every screen: both dashboards, the home page, Members, Loans, and every admin area.

### 11.3 Logout confirmation

Clicking **Log out** opens a modal confirmation (`role="dialog"`, `aria-modal="true"`, labelled by its heading, Escape and backdrop click close it, Cancel receives focus):

- **Cancel** keeps the session and closes the dialog.
- **Log out** calls the existing `logout()` and returns to `/login`.

Because the control is shared, the confirmation applies everywhere, not just the dashboards.

### 11.4 Tests

- `lib/names.test.ts` (8): two-part, three-part, four-part abbreviation, comma-preserved, single-word/blank, plus the `userDisplayName` fallbacks.
- `lib/greeting.test.ts` (3): every branch boundary, including midnight and 04:59 counting as morning.
- `components/ui/DashboardHeader/index.test.tsx` (8): welcome with identity, no change before 5s, greeting after 5s (fake timers, fixed clock), greeting following the clock across noon while open, plain fallback, Cancel keeps session, confirm logs out once, Escape closes without logging out.
- `components/dashboard/DashboardView/index.test.tsx` (2) and updated `components/admin-dashboard/AdminDashboardView/index.test.tsx` (name above log out, linked-member preference).
- `backend/tests/test_auth.py` (+2): `/auth/me` reports the member's stored name; an unlinked admin gets `null` while a linked one gets the member's name. File run: 10 passed.

### 11.5 Results

- Frontend: **27 files / 170 tests passed**; `npx tsc --noEmit` exit 0; `npm run build` compiled successfully.
- Browser-verified on the local production build: the member dashboard greets as `Good morning, Okafor, Adaeze` with the name above Log out, and the same identity line and confirmation appear on admin screens.
- Changes are **not committed or pushed**.

---

## 12. Structured member names and role-aware identity (2026-11-14)

### 12.1 Design

Names are now stored as parts **and** as the printed string, so every existing screen keeps printing correctly without touching its display code, while registration captures the parts explicitly:

- `members` gains `first_name`, `last_name`, `other_names` (all nullable). `name` remains the authoritative printed form, composed as **`Last, First Other(s)`** (e.g. `Okafor, Adaeze Ngozi`) whenever the parts change.
- Requests may still send `name` alone (legacy importers/tests); the router stores it unchanged and leaves the parts null. Sending any part requires both `first_name` and `last_name` (422 otherwise), and a part update recomposes `name`.
- Search matches the stored printed `name`, the legacy `First Other Last` concatenation, PSN, and phone, so both name orders and partial parts find a member.

### 12.2 Migration

`scripts/manual_migration_2026_11_member_name_parts.sql` (registered in `ORDERED_MIGRATIONS`):

- adds the three columns idempotently;
- for every row whose parts are all null, parses existing `name` — comma form: family before the comma, first word after it as given name, the rest as other names; whitespace form: **the ledger writes names family-first**, so the first token is the family name, the second the given name and the rest other names; a single word is left untouched — and rewrites `name` to the canonical `Last, First Other(s)` form.

**Run this migration against production/Neon before deploying this build.** Without it the API inserts/updates fail on the missing columns, and existing rows keep their old order until backfilled. The local sandbox was migrated and verified (e.g. `Ada Obi` → `Obi, Ada`, parts populated).

### 12.3 Form and display

- The Add/Edit member form captures **PSN \***, **Last name \***, **First name \***, **Other name(s)** in that order; the required inputs carry both a visible `*` and the HTML `required` attribute. Next of kin is labelled `Next of kin *` on create (an explicit Yes/No answer is mandatory) and unstarred on edit. Editing prefills from the stored parts, falling back to parsing `name` for records created before the split.
- `lib/names.ts`: `lastNameFirst()` prints `Last, First Other(s)` and abbreviates second-and-later given names with a period (`Okafor, Adaeze N. C.`); `splitStoredName()` feeds the edit form; `userDisplayName()` is role-aware.
- **Admin identity:** the line above Log out is always `user.username` on admin screens (the greeting may still use the linked member's name). **Member identity:** the full printed name; only the dashboard heading abbreviates other names (`Welcome, Okafor, Adaeze C.` above the full `Okafor, Adaeze Chika`).
- Fixed a pre-existing create blocker found during browser verification: the form sent `gender: ""`, which the API rejects as an invalid enum (422). Blank gender is now omitted from the payload, leaving an existing member's value untouched.

### 12.4 Tests and verification

- Backend: new `tests/test_member_name_parts.py` (7) — composition, optional other names, legacy single-name payload, missing name 422, search across orders/parts, recomposition on update incl. clearing other names, refusing to drop the family name. Name-related files: **72 passed** against `mact_test`.
- Frontend: `lib/names.test.ts` (13), `useMembersPage.test.ts` (12, incl. prefill from legacy name, preferring stored parts, create sending parts and never `name`/blank `gender`), new `MemberForm/index.test.tsx` (3: field order, asterisks/required attributes, edit mode), plus updated dashboard/admin-dashboard header tests.
- Frontend: **28 files / 181 tests passed**; `npx tsc --noEmit` exit 0; `npm run build` compiled successfully (20/20 static pages).
- Browser-verified on the local sandbox: admin identity `localadmin` above Log out; form order and asterisks; creating `MCT-9102` produced `Okafor, Adaeze Ngozi Chika`; search by `Adaeze Okafor` found it; Edit prefilled all three fields; member dashboard greeted `Okafor, Adaeze C.` with the full name above Log out. The temporary test member and name tweak were removed afterwards.

### 12.5 Production rollout (2026-11-14)

- The ordered runner applied the migration to production Neon (`16 applied, 1 already`) and backfilled all 191 members.
- **Correction:** the first release of the file assumed the last token was the family name (matching the local seed data, which is typed given-name-first). The real ledger is **family-first** (`Atagher Nguwasen Priscilla`, `Lanshima Gandepuun`), so that run inverted every row. The file's whitespace rule was changed to first-token family, the backfill was reset and re-run atomically against production, and the result verified: 191 rows, 0 null parts, 0 composed-name mismatches; e.g. `10468` is now `Atagher, Nguwasen Priscilla`.
- Five ledger rows were typed given-name-first and were corrected explicitly: `7294 Iortim, Joseph Nyijime`, `4988 Adue, Matthew Pauline`, `36020 Shagher, Beatrice`, `36023 Mlumun, Christiana Upaa`, `36029 Onu, Sunday`.
- Four rows remain ambiguous and should be checked in the member edit form: `32061 Jon- Uan Washima`, `32087 Hon Helen Mbatomon`, `32261 Adi Yese Mchivir Loisa`, `36024 Dooyum Torikpa`.
- `scripts/migrate_members_from_xlsx.py` now splits family-first too, so a future import does not reintroduce the inversion.

## 13. Responsive layout and shared modal (2026-11-15)

### 13.1 Approach

Layout and responsive rules moved out of inline `style={{}}` objects into **external CSS**, as requested: `app/globals.css` (imported once in `app/layout.tsx`) plus component CSS modules where a component owns its markup. No Tailwind was introduced; the existing plain-CSS system is kept.

- `.page` gives every screen fluid padding (`clamp(12px, 4vw, 32px)`, tightened to `16px 12px` under 640px) with `.page--640/700/900/1000/1100/1200` width caps. Every view and loading state now uses it.
- `.page-header` is a wrapping title/action row; `.toolbar` is a wrapping action/filter row (`8px 12px` gaps) with `.toolbar--end` for right-aligned groups.
- `.form-grid` is a self-collapsing grid (`repeat(auto-fit, minmax(min(220px, 100%), 1fr))`); `.form-grid__full` spans every column. Used by the member form, the disburse form, the loan-type and rate-history forms.
- `.search-field` grows to full width on phones and never forces the page wider. `.auth-card` gives the four standalone auth screens fluid margins/padding inside a 420px cap.
- `.table-scroll` remains the safety net for wide tables.

### 13.2 Tables as stacked cards

`components/ui/Table` now wraps every table in `.table-scroll` and reads the `<thead>` labels once, cloning them onto each body cell as `data-label` (spanning rows such as an inline reset-password form are skipped). Under 640px the CSS hides the header row and renders each `<tr>` as a bordered card with `label — value` rows; action cells wrap. `@media print` restores the normal table, which keeps the printable deduction schedule unchanged.

All fourteen tables go through this component, so no per-table markup was needed.

### 13.3 Shared modal

The accessible modal from the payroll Enter form (focus move/restore, Escape, focus trap, backdrop-only click, busy lock) is now `components/ui/Modal` and is reused by:

- the deduction form (`DeductionForm`), unchanged externally;
- the **Add/Edit member form**, which is now a dialog with the same Close button, hint and busy lock (opened by the new **Add member** button, and by **Edit**), single-column on phones;
- the audit detail dialog, the deduction reason dialog, the contribution change request dialog and the Log out confirmation.

The member form's page hook gained `isOpen`/`busy`/`openCreate`/`close`, with `saving` state wrapped around the API call so the dialog cannot be dismissed mid-save.

### 13.4 Other responsive fixes

- Header/nav link groups, filters, pagination, bulk-action bars, review actions and form button rows now wrap instead of overflowing.
- Fixed widths were replaced with fluid ones: member search (320px), admin member picker (260px) and the reset-password input (320px).
- Admin dashboard card grids use `minmax(min(260px, 100%), 1fr)` so they never overflow a phone.
- Dense deduction worklist/review rows wrap their title and status line.

### 13.5 Verification

- `npx tsc --noEmit` exit 0.
- Vitest: **28 files / 184 tests passed** (3 new member-modal tests: labelled dialog for create/edit, close by button and Escape, busy lock).
- `npm run build` compiled successfully (20/20 static pages).
- Browser-checked on the local sandbox with the app in a **375px-wide frame**: members header wraps under the title; search and filters stack; the member table renders as labelled cards with intact values; the Add member dialog fits with single-column fields; the deductions ledger stacks into cards with no horizontal page scroll (`scrollWidth` 356 under a 371px viewport); the Enter-deduction dialog stacks its fields. Desktop (1200px) still renders normal tables (`display: table-cell`), confirming the media-query switch.

## 14. Member list details modal and confirmation steps (2026-11-15)

### 14.1 Compact member list

The wide members table (PSN, name, department, status, restricted, phone, next of kin, login, actions) is now a three-column list: **PSN**, **Name** (with the conflict marker where applicable) and a **Details** text link. Everything else moved into a dialog, so the list stays readable on phones and the page no longer competes with dense action rows.

### 14.2 Member details modal

`components/members/MemberDetailsModal` (built on the shared modal) shows the full record — PSN, status and exit date, department, gender, phone, email, bank, account number, monthly contribution and its effective date, restriction flag/reason, login state, and the complete next-of-kin block. The actions (**Edit member**, **Delete member**, **Create/Deactivate/Reactivate login**, **Record exit**) render as underlined text links in a `.link-list`, not buttons, and derive from the same state as before (login action from `login_account_status`, no exit link once dated). Conflicted members are fully readable but show the conflict notice instead of actions. Edit replaces the details dialog with the form rather than stacking two dialogs.

The selected member is tracked by id in `useMembersPage` and derived from the current list, so the dialog always shows fresh data after an action and disappears on its own when the member is deleted or filtered out.

### 14.3 Page order

The contribution change request panel now sits directly under the page feedback, above everything member-related. A **Member records** section (heading, Add member, search, filters, count, list) follows it. The contribution panel's own layout is unchanged, as requested: inline review reason plus Approve/Reject.

### 14.4 Confirmation before risky actions

New shared `components/ui/ConfirmDialog` (modal-based; Cancel holds initial focus so Enter does not confirm) now asks once more before:

- deleting a member;
- deactivating or reactivating a login;
- approving or rejecting a contribution change request.

The confirmation names the member and states the consequence (e.g. the amount and the next-month effective rule). The action runs only on confirm; a backend refusal keeps the dialog open with the reason shown inside it. Member confirmations live in the page hook (`confirmation` state); the contribution panel keeps its own so the typed review reason survives until the decision lands. Create login and Record exit keep their existing reason/password prompts, which already require deliberate input.

### 14.5 Verification

- `npx tsc --noEmit` exit 0.
- Vitest: **30 files / 196 tests passed**, including new tests for the details modal (fields, state-driven login action, conflicted read-only), the compact list, the details hook state, and confirmation-gated delete/login/contribution decisions.
- `npm run build` compiled successfully (20/20 static pages).
- Browser-checked on the local sandbox: details → Edit swaps in the pre-filled form; Details → Delete member opens the confirmation with Cancel focused; Approve on a pending contribution opens the amount confirmation; cancelling sends nothing. At 375px the list renders as labelled cards with the Details link, and the details dialog is a single column with the action links wrapped under a rule; at 1200px the list is a normal table, the details dialog is 640px wide with a three-column field grid, and there is no horizontal overflow.

## 15. Admin navigation submenus (2026-11-15)

### 15.1 Menu structure

The flat admin menu is now grouped so related screens stay together as the application grows:

- **Dashboard** — top-level link.
- **Members** — top-level link, members module only.
- **Loan Management** — menu (loans module only): Loans, Loan applications, Disbursements, Loan repayments. Future loan screens belong here.
- **Payroll deductions** — top-level link, deductions module only.
- **Settings** — menu: Staff / Admin users, Offices, Roles and permissions, Cooperative settings (the `/admin/settings` page). Future configuration screens belong here.
- **Audit log** — top-level link.

`useAdminNav` returns ordered `items` where each item is either a link or a group with children, so adding a screen to a section is a one-line change. Module gating is unchanged: a group appears only when its module is enabled, and the menu still falls back to the core areas if settings cannot be loaded.

### 15.2 Behaviour

Groups render as buttons with `aria-expanded` and `aria-controls`; the submenu is an absolutely positioned dropdown on desktop and an indented static list inside the mobile drawer. Hovering a group with a mouse opens its submenu and moving the pointer away closes it, so only one menu is open at a time; clicking keeps it open for mouse users while touch and keyboard clicks toggle it. The group containing the current pathname opens automatically, but following one of its links closes the menu and the destination page stays closed. Because every page renders its own AdminShell, the navigation remounts on route changes, so the dismissal is recorded in `sessionStorage` for the destination path and cleared as soon as the officer moves elsewhere; landing on another page (or reloading and moving on) restores the auto-open. Links inside a submenu carry `aria-current="page"` like top-level links. Escape closes open dropdowns (after closing the mobile drawer, which still returns focus to the Menu button), clicking outside the navigation closes them, and following any link closes the mobile drawer.

The admin dashboard mirrors the same grouping: **Members**, **Loan Management** (now including a **Loans** card for `/loans`), **Deductions**, **Settings** (Staff / Admin users, Offices, Roles and permissions, Cooperative settings) and **Audit**.

### 15.3 Verification

- `npx tsc --noEmit` exit 0.
- Vitest: **30 files / 209 tests passed**, including rewritten navigation tests for the grouped items, module gating of the Loan Management menu, hover open/close and pointer switching between menus, accordion behaviour, keyboard toggling, active-section auto-open, dismissal that survives the nav remounting after a link click, Escape and outside-click closing, and mobile link handling, plus dashboard tests for the new headings, the Loans card and the renamed Cooperative settings link.
- `npm run build` compiled successfully (20/20 static pages).
- Browser-checked at 1200px: hovering Loan Management opens its dropdown, moving to Settings swaps the open menu, and moving away closes it; `/admin/disbursements` opens the group automatically with the button marked active; following Offices from Settings navigates to `/admin/offices` with the menu closed and Offices marked current. At 375px the Menu button opens the drawer; Settings expands inline with an indented, bordered list and no horizontal overflow (document width 360px inside a 375px viewport).
