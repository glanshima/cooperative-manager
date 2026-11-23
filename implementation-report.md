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

## 16. Brand foundation and shell (2026-11-18)

### 16.1 Foundation

Koperra's identity package is now part of the app without displacing the cooperative's own identity:

- Brand files live under `frontend/public/brand` (horizontal, stacked, dark, symbol and wordmark logos, tokens reference) and `frontend/public/icons` (favicon SVG/PNG and app icon). The favicon and app icon are wired through the root metadata; the generated title is "MACT Cooperative Manager".
- `frontend/lib/branding.ts` is the single source for the cooperative name, short name and monogram (placeholder "M" until a logo is uploaded) and for the platform name and credit ("Koperra", "Koperra by SIDGAKS Tech").
- `components/branding/CooperativeBrand` renders the cooperative's mark and name, with an optional logo URL and an inverse tone for dark surfaces. `components/branding/PlatformAttribution` renders the discreet "Powered by Koperra" credit, with the same tone option.
- Inter is loaded with `next/font` (self-hosted at build time, `display: swap`) and exposed as `--font-inter`; the body font stack falls back to Manrope and the system stack.
- `app/globals.css` now opens with a token layer: the Koperra palette, semantic surface/border/text tokens, action and status colours, radii and shadows, the `--sidebar-width` and a single z-index scale (`--z-dropdown: 20`, `--z-sticky: 30`, `--z-drawer: 40`, `--z-modal: 100`, `--z-confirm: 110`). The dead `.modal-backdrop`/`.modal-card` classes were removed and the shared Modal now sits on `var(--z-modal)`.
- Shared primitives were added for `.btn` with primary/secondary/ghost/danger variants, status `.badge` tones, `.num` tabular numerals, a reduced-motion-aware `.skeleton`, a global focus-visible ring, and base input/button styling built on the tokens.

The self-hosted font was verified by a production build before any layout work continued, so the build does not depend on a network fetch at deploy time.

### 16.2 Shell

`app/admin`, `app/members` and `app/loans` moved into the `app/(admin)` route group behind one `app/(admin)/layout.tsx`, so `AdminShell` mounts once and survives navigation. URLs are unchanged. Pages no longer wrap themselves in the shell; they keep their own `useAuth` guard and return a shared `PageSkeleton` (title, action, cards and table blocks, announced as a busy status) while authentication or page data loads. The module gate and the admin views that previously printed "Loading..." use the same skeleton.

`AdminNav` is rebuilt as the shell's navigation:

- **Wide screens** get a fixed 264px navy sidebar with the cooperative brand at the top, the menu in the middle and the "Powered by Koperra" credit in the footer. The page content is offset by the sidebar width.
- **≤900px** gets a sticky top bar with the cooperative brand and a Menu button, and the same sidebar as an off-canvas drawer with a scrim, a close button, Escape handling (focus returns to the Menu button) and a scroll lock while open.
- Groups use `aria-expanded`/`aria-controls` and an accordion: one section open at a time, and the section containing the current page opens automatically. Links carry `aria-current="page"`, and the active row is marked with a lime inset bar.

One deliberate change from the earlier top-bar dropdowns: in the persistent sidebar the section stays expanded after one of its links is followed, because collapsing it would hide the officer's own current location. Clicking the group button still closes it manually, and the mobile drawer closes on every link.

### 16.3 Verification

- `npx tsc --noEmit` exit 0.
- Vitest: **30 files / 208 tests passed**, including rewritten navigation tests for the brand and platform credit, the sidebar landmarks, module gating, active-section auto-open and persistence, the accordion, keyboard toggling, Escape, and the mobile drawer (toggle, close button, Escape with focus return, closing on links).
- `npm run build` compiled successfully (20/20 static pages, routes unchanged).
- Browser-checked with a temporary shell preview at desktop and phone widths: at 1200px the 264px navy sidebar sits beside an offset content area with the brand at the top and the credit at the bottom; the sidebar rows align with the table content. At 375px the top bar shows the brand and Menu button, the page stacks without horizontal overflow, and Menu opens the navy drawer over a scrim with the close button, indented Settings list and the footer credit. The preview route was removed after the check.


## 17. Branded auth screens and member dashboard (2026-11-18)

### 17.1 Auth screens

The four standalone auth screens now share a `components/branding/AuthShell`:

- The cooperative mark and name sit in a bordered header row inside the card, so a login looks like it belongs to MACT before it says anything else.
- The card is centred in the viewport and the "Powered by Koperra" credit is pinned below it with `margin-top: auto`, so the platform mark is visible without competing with the cooperative.
- `login`, `forgot-password`, `reset-password` and `change-password` all render through the shell; page headings were aligned to sentence case ("Log in", "Forgot password", "Set a new password", "Change your password").

Alongside the shell, the inline styles on those pages were brought back onto the token layer:

- Submit buttons use `.btn btn-primary`; inputs drop their per-page padding/font/border overrides and inherit the global token styles.
- Status boxes (login errors, the forgot-password confirmation, the reset-link invalid/success states and the in-form error) now use new `.notice`, `.notice--error` and `.notice--success` utilities backed by `--danger-border`, `--success-border`, `--danger-soft` and `--success-soft` tokens, replacing four copies of hardcoded hex boxes.
- Muted copy uses `var(--text-muted)` instead of `#666`, and the change-password loading state uses the shared `PageSkeleton`.

### 17.2 Member dashboard

`DashboardView` keeps its layout but gains the brand marks:

- A full-width brand row sits above the greeting header (`DashboardView.module.css` `.brandBar`, closed with a hairline border), and the "Powered by Koperra" credit closes the page in a bordered footer beneath the loan sections.
- The disabled-loans notice uses `var(--border)` instead of the stray `#ddd`.

The greeting, PSN and log-out controls are unchanged; the dashboard's cooperative identity is now present at the top and the platform credit at the bottom, matching the shell and auth screens.

### 17.3 Verification

- `npx tsc --noEmit` via `next build` exit 0.
- Vitest: **31 files / 210 tests passed**. New assertions: the login page renders the "Log in" heading plus "MACT Cooperative" and "Koperra"; `DashboardView` renders both brand marks next to the existing greeting assertions; a dedicated `AuthShell` test covers child rendering and the brand/credit pairing.
- `npm run build` compiled successfully (20/20 static pages, routes unchanged after the temporary preview routes were removed).
- Browser-checked at phone width (429px) and 1200px through a temporary preview route and a scaled iframe harness (both removed afterwards): login, forgot-password and the invalid reset-link state all show the brand row inside the card, the credit below it around the fold, and the branded error notice; the member dashboard shows the brand row above "My Dashboard", the content sections and the credit under the last section at both widths, with no horizontal overflow.


## 18. Editable cooperative branding (2026-11-19)

### 18.1 Data and API

- `backend/app/models.py` / manual migration `scripts/manual_migration_2026_11_cooperative_branding.sql` add four settings columns: `cooperative_name` (120), `cooperative_short_name` (32), `cooperative_monogram` (8), all NOT NULL with MACT defaults, and nullable `logo_url` (500). The migration is idempotent (`ADD COLUMN IF NOT EXISTS`), and was re-applied to the sandbox test database to confirm it.
- `GET /api/branding` is public and returns only the branding slice (name, short name, monogram, logo URL). It never creates a settings row; when none exists it answers with the deployment defaults, so signed-out screens always have an identity.
- `PUT /api/settings` accepts the three text fields, collapses internal whitespace and rejects blank values. Changes are audited with previous/new values like the other settings.
- `POST /api/settings/logo` takes `{content_type, image_base64}` (matching the existing base64 receipt convention, so no multipart dependency), decodes the bytes, sniffs the magic number and rejects a mismatch with the declared type (SVG and other formats are refused), enforces 1 MB, and stores the file in Vercel Blob under `branding/cooperative-logo-*.{png,jpg,webp}`. Missing `BLOB_READ_WRITE_TOKEN` answers 503; a storage failure answers 502. The replaced blob is deleted best-effort after the new URL is committed.
- `DELETE /api/settings/logo` is idempotent when no logo exists, keeps the stored URL if Blob deletion fails (so settings never point at a deleted file), and clears + audits on success.
- `backend/app/blob_storage.py` is a small REST client (`PUT /api/blob`, `POST /api/blob/delete`, `x-api-version: 11`); logos are raster-only to keep stored SVG out of a public URL.

### 18.2 Frontend

- `lib/api/branding.ts` (`getBranding`) and `lib/api/settings.ts` (`uploadLogo`, `deleteLogo`, branding fields on `Settings`) mirror the endpoints; `lib/api/index.ts` exports them.
- `components/branding/BrandingProvider` is mounted once in the root layout and fetches `/api/branding` after paint. It starts from the `lib/branding.ts` constants and keeps them on failure, so no screen waits on branding. `useBranding` also exposes `setBranding`, which the settings hook and logo controls call after a save/upload so the sidebar and brand update without a reload.
- `CooperativeBrand` now defaults its name, monogram and logo from the provider; explicit props still win (used to force a preview or the monogram).
- `SettingsView` opens with `components/admin-settings/BrandingSection`: name/short name/monogram fields, a live logo preview (monogram placeholder when none), a file picker restricted to PNG/JPEG/WebP with a 1 MB client-side check, Upload and Remove buttons, and a dismissible success/error message that clears after 10 seconds. A chosen file previews before upload; uploads send base64 JSON and only the returned `logo_url` is copied into the form, so unsaved text edits are not discarded. Below 480px the preview and its caption stack.
- `README.md`, `DEPLOYMENT.md` and `backend/.env.example` document `BLOB_READ_WRITE_TOKEN`, the 503 behaviour without it, and that the tab title/favicon still come from the static `metadata` export (they need a deploy to change).

### 18.3 Verification

- Backend: `pytest` on the sandbox test database **320 passed** (15 new branding tests: public defaults without creating a row, branding-only exposure, whitespace/blank/over-length validation and audit, permission 403, upload path/extension/audit, declared-type mismatch, non-image bytes, SVG rejection, missing token 503, replacement deletes the old blob, removal audits, removal failure keeps the URL). The branding migration was re-applied to prove idempotence.
- Frontend: `npx tsc --noEmit` exit 0; Vitest **35 files / 228 tests passed** (new coverage for the provider's defaults/fetch/failure/update path, `CooperativeBrand` overrides and logo rendering, the branding section's fields, 1 MB and type rejection, base64 upload payload, failure message and removal, plus the API method/body mappings). `npm run build` compiled successfully (20/20 static pages).
- Browser-checked through a temporary preview route (removed afterwards) at 1200px and at the 429px browser width: the identity section renders first with the three fields, the monogram placeholder, the file picker and a disabled Upload button; with a logo URL it shows the image capped at 48px, a "Current logo" caption and the Remove button; the page stacks without horizontal overflow. The live logo upload round-trip was not exercised in the browser because the sandbox has no Blob token — the 503 path is covered by the backend tests, and the upload/delete wire format by the frontend API tests.


## 19. Resend activation and email workflow verification (2026-11-19)

### 19.1 Delivery foundation

- `backend/app/email_utils.py` was rewritten around an explicit result contract. `send_email()` never raises and never retries; it returns an `EmailResult(ok, status, message_id, retryable, detail)` whose status separates `skipped` (missing key/sender/recipient, invalid recipient), `rejected` (4xx validation), `unauthorized` (401/403), `rate_limited` (429), `provider_error` (5xx), `network_error` and `timeout`. Callers log non-delivery with the status only.
- Configuration is read at call time from `RESEND_API_KEY` and `FROM_EMAIL`. A bare `FROM_EMAIL` takes the cooperative name (from Settings, via `backend/app/cooperative_branding.py`) as the display name; an explicit `"Name <address>"` wins. Timeouts are 5 s connect / 10 s read. An optional `idempotency_key` becomes the Resend `Idempotency-Key` header; there are no automatic retries, so duplicate-send risk is unchanged.
- The provider response body is never copied into results or logs; only the short machine-readable error name (charset-checked) is used. Recipient addresses, subjects and credentials are not logged.
- Templates now render the cooperative identity, escape every interpolated value (member names, loan types, reasons, bank details), use the brand colours, and always include a generated plain-text alternative.
- `backend/app/cooperative_branding.py` is the single source of identity fallbacks, shared by `GET /api/branding` and the email templates.

### 19.2 Configuration and real delivery gate

- `RESEND_API_KEY` and `FROM_EMAIL=noreply@mail.sidgakstech.me` are set in `backend/.env` (gitignored, never committed). `.env.example`, `DEPLOYMENT.md` and `README.md` document the variables with placeholders only.
- A first send to the owner-approved recipient with `.net` was refused 403 (`This API key is not authorized to send emails from mail.sidgakstech.net`): the verified domain is `.me`, not `.net`. The `.me` attempt was accepted by Resend on 2026-11-19 (message id `01a1f461-51e2-79cf-a1bf-aa19ca63a6b3`, sender `MACT Cooperative <noreply@mail.sidgakstech.me>`), and the owner confirmed arrival in the destination inbox. Resend is therefore operational.
- `scripts/send_test_email.py <recipient>` performs that gate on demand and prints the status and message id, never the key.

### 19.3 Workflow verification

All six existing workflows send after the business commit; the loan-form payment rejection was previously the exception (sent before `db.commit()`) and now sends afterwards, so a mail failure cannot follow a rolled-back decision. Recipients are resolved from stored member records (`Member.email`), never from request payloads.

| Workflow | Trigger | Recipient | Subject | Idempotency key |
|---|---|---|---|---|
| Password recovery | `POST /api/auth/forgot-password` (after token commit) | User's linked email | `Password Reset Request - <cooperative>` | none (each request is a new token) |
| Loan disbursed | `POST /api/loan-applications/{id}/disburse` (after commit) | Member | Your loan has been disbursed | `loan-disbursed:<loan_id>` |
| Loan application rejected | `POST /api/loan-applications/{id}/decide` rejected (after commit) | Member | Update on your loan application | `loan-rejected:<application_id>` |
| Loan form payment rejected | `POST /api/loan-applications/{id}/verify-payment` rejected | Member | Your loan form payment could not be verified | `loan-payment-rejected:<application_id>` |
| Repayment verified | `POST /api/loan-repayments/{id}/verify` approved (after commit) | Member | Repayment received | `repayment-verified:<repayment_id>` |
| Repayment rejected | `POST /api/loan-repayments/{id}/verify` rejected (after commit) | Member | Your repayment could not be verified | `repayment-rejected:<repayment_id>` |

Approval of a loan application still sends no email, preserving the existing product decision (the disbursement email is the single detailed notice).

### 19.4 Verification

- Backend: `pytest` on the sandbox test database **341 passed** (21 new: 16 provider-contract tests covering success, missing key, missing/invalid sender, invalid recipient, 400/401/429/500, connection error, timeout, secret-free logs, idempotency forwarding, commit isolation and template escaping, plus 5 endpoint-level workflow tests for disbursement, payment-rejection ordering, repayment verification/rejection and password recovery).
- Real delivery: provider accepted and the owner confirmed inbox receipt (19.2).
- Not yet done (later phases of the plan): in-app notification centre, web push, Novu (parked by decision).

## 20. Sidebar account control and the production branding migration (2026-11-19)

### 20.1 Production schema drift

- `fad8500` deployed the branding settings columns before the migration reached production. Public `GET /api/branding` answered 500 while `/api/health` was 200; the authenticated `GET /api/settings` 500 reached the browser as "Could not reach the server" (serverless error responses carry no CORS headers), and the admin sidebar lost Members / Loan Management / Payroll deductions because `useAdminNav` only adds module links after settings load.
- `scripts/apply_manual_migrations.py` did not list `manual_migration_2026_11_cooperative_branding.sql`; it is now the last entry in `ORDERED_MIGRATIONS`, so a migration cannot ship without the runner knowing it.
- Applied to production (branch `br-rough-flower-aycl78im`) on 2026-11-19 with explicit owner approval: 17 files applied, 1 already applied, server-default parity re-checked. Verified afterwards: `/api/branding` 200 with the deployment defaults, `/api/settings` 401 without a token. No rows were created or changed.

### 20.2 Sidebar account control

- `LogoutControl` gained a `sidebar` variant: username on the left (ellipsis when long) and "Log out" as a text link on the right, sitting above "Powered by Koperra" in the sidebar footer. The existing confirmation dialog is unchanged.
- `AdminNav` reads the session with the existing `useAuth()`, so every admin screen offers log out — previously only the two dashboards rendered the control.
- `DashboardHeader`'s log-out control is now optional: the admin dashboard passes only the greeting, while the member dashboard keeps identity above Log out because it has no sidebar.
- Verification: `npx tsc --noEmit` clean; Vitest **35 files / 230 tests passed** (sidebar account tests added; admin dashboard tests updated for the moved control); `npm run build` 20/20 static pages. A browser screenshot was not taken because the local sign-in flow was blocked by the credential guard; layout and behaviour were verified through the component tests only.

## 21. In-app notifications (2026-11-19)

### 21.1 Data and API

- New `notifications` table (`backend/app/models.py`): `user_id` (FK `users`, cascade), `category` enum (`loan | repayment | contribution | account | system`), `title` (200), `body` (1000), `link_path` (255), `is_read` + `read_at`, `created_at`; index `(user_id, created_at DESC)` matching the bell's "newest first per user" query. Idempotent manual migration `scripts/manual_migration_2026_11_notifications.sql`, registered in `ORDERED_MIGRATIONS`.
- `backend/app/notification_service.py` — `notify()` queues a row and `notify_member()` resolves the member's `role='member'` login (skipping members with no login or an inactive account). Both are called *inside* the same transaction as the change, so a notice rolls back with its change; email remains post-commit.
- `routers/notifications.py`, mounted at `/api/notifications`:
  - `GET ""` — newest first, `skip`/`limit` (max 100), returns `{items, total, unread_count}` so one poll feeds both the panel and the badge.
  - `POST /read-all` — marks only the caller's unread rows, returns `{updated}`.
  - `POST /{id}/read` — idempotent; an id belonging to another account is a 404.
  - Every route filters on `current_user.id` from the token; no user id is ever accepted from the request.

### 21.2 Producers (each written before its flow's commit)

| Event | Category | Title |
|---|---|---|
| Loan form payment verified / rejected | loan | Loan form payment verified / could not be verified |
| Loan application approved / rejected | loan | Loan application approved / not approved |
| Loan disbursed | loan | Loan disbursed |
| Repayment verified / rejected | repayment | Repayment verified / not verified |
| Contribution change approved / rejected | contribution | Contribution change approved / not approved |

Notify copy is stored as final rendered text, so later wording or policy changes never rewrite what a member was told. All member-facing links point at `/dashboard`.

### 21.3 Frontend

- `lib/api/notifications.ts` (`getNotifications`, `markNotificationRead`, `markAllNotificationsRead`) and `components/notifications/hooks/useNotifications.ts` (mount + 60 s poll, optimistic mark read / mark all, refetch on open).
- `components/notifications/NotificationBell` — icon button with an unread badge (`99+` cap) and an accessible label (`Notifications, 3 unread`); the panel is portalled to `document.body` and anchored to the button's live rect, because the sidebar scrolls, clips overflow and is transformed on phones. Escape closes and returns focus; outside click closes; choosing a notice marks it read and follows its link.
- Placement: in the member dashboard header via a new optional `actions` slot on `DashboardHeader`; in the admin shell via `useMediaQuery` (`lib/useMediaQuery.ts`) so exactly one bell is mounted — the top bar at ≤900px, the `AdminNav` brand row above that. Placing it in the brand row at every width squeezed the (customisable) cooperative name to an ellipsis inside the drawer.

### 21.4 Verification

- Backend: `pytest` on the sandbox test database **351 passed** (10 new: scoping, ordering/totals, cross-account 404, idempotent read, read-all scoping, three producer paths, no-login member, 401).
- Migration: applied to the local sandbox via the runner (18 applied, 1 already applied); `notifications` columns and `ix_notifications_user_created` confirmed.
- Routes: a throwaway backend on port 8010 (sandbox DB) answered `/api/health` 200 and `/api/notifications` + `/read-all` 401 without a token; instance stopped afterwards.
- Frontend: `npx tsc --noEmit` clean; Vitest **36 files / 239 tests passed** (8 bell tests; a placement test asserting which container mounts the bell at each breakpoint; AdminNav mocks extended for the bell and `matchMedia`); `npm run build` 20/20 static pages (run before the bell-placement tweak, which was verified by typecheck + tests + browser only because the dev server held `.next`). Note: the first full-suite run reported 2 failures that did not reproduce — later full runs were clean.
- Signed-in browser pass (local sandbox, `localhost:3000` against `127.0.0.1:8000`): the member bell showed the empty state, then "3 unread" with newest-first entries; **Mark all as read** cleared dots, tint and badge; Escape closed and returned focus; outside click closed; clicking an unread item marked it read, closed the panel and routed via `link_path`; read state survived a reload; a notification inserted mid-session appeared through the 60 s poll with no reload. On the admin side the bell sits in the mobile top bar and the drawer shows the full cooperative name; its panel portals out of the drawer to the viewport.
- Broadcast caveat: the admin bell is empty in practice because every producer currently targets a member account; the router is user-scoped so staff notifications can be added later without schema changes.

## 22. Permission-scoped admin navigation (2026-11-20)

### 22.1 Resolved permissions on the session

- `app/deps.py` gained `user_permission_codes(db, user)`: members get `[]`, a super admin gets `sorted(PERMISSION_CODES)` from the catalogue itself, and every other admin gets the distinct codes reachable through active `UserRoleAssignment → Role → RolePermission` rows. Reading the catalogue (not the table) for super admins means a deployment whose `permissions` table lags the code still reports the full set.
- `UserOut.permissions` (`schemas.py`) carries the list; `GET /api/auth/me` fills it, so the client resolves navigation from the same data the server enforces.

### 22.2 Branding permissions and tightened auth routes

- Catalogue additions `branding.view` (Branding) and `branding.manage` (Branding). `DEFAULT_ROLES` is unchanged; super admins hold them through the catalogue rule above.
- `PUT /api/settings` stays admin-only but is field-scoped: branding fields (`cooperative_name`, `cooperative_short_name`, `cooperative_monogram`) require `branding.manage`; any other field requires `admin.settings_manage`. `POST`/`DELETE /api/settings/logo` require `branding.manage`. `GET /api/settings` is unchanged.
- `POST /api/auth/create-member-login` and `POST /api/auth/reset-member-password` now require `member.update` instead of bare admin, and the permission-catalogue drift test still passes (no uncatalogued string literals).

### 22.3 Frontend

- `lib/permissions.ts` (`hasPermission`, `hasAnyPermission`, plus the disbursement and settings-page code groups).
- `useAdminNav(permissions)` filters every link: Dashboard is ungated; Members needs `member.view` + module; Loans and Loan applications `loan.view`; Disbursements any disbursement code; Repayments `repayment.view`; Deductions `deduction.view` + module; Audit `audit.view`; Settings children by `admin.user_manage` / `admin.office_manage` / `admin.role_manage` / `branding.view|manage`. A group renders only when its module is on and it has children left.
- `AdminNav` runs the shell auth guard (`useAuth({requireAuth, requirePasswordChanged, requireRole:"admin"})`) and renders nothing until `/me` resolves, so a member never sees admin chrome flash. `app/(admin)/admin/page.tsx` redirects to `/admin/dashboard`, removing the duplicate landing page.
- Settings save is split into two scopes (`SCOPE_FIELDS`) so a partial-permission officer only PUTs the fields they may change. `BrandingSection` gained `readOnly`, which disables the three identity inputs and hides upload/remove when the officer holds `branding.view` only, with the required permission named on screen. New Platform section renders `PLATFORM_CREDIT`.
- `HomeView` gates each link with the same helpers; members now see only the member dashboard, since `/loans` is admin-only.

### 22.4 Verification

- Backend: `pytest` on the sandbox test database **359 passed**; focused rerun of the changed suites **62 passed**.
- Frontend: `npx tsc --noEmit` clean; Vitest **36 files / 247 tests passed**; `npm run build` 21 static routes including `/admin`.
- No ESLint config exists in the repo, so `next lint` was not run.

### 22.5 Deploy note

- Shipped as `de65673`. The new permission rows must exist in the target database — `scripts/seed_permissions.py` is idempotent and only upserts permissions by code (existing role grants are untouched). It was run against the production branch `br-rough-flower-aycl78im` on 2026-11-20 (43 permissions seeded/updated; all five default roles already existed).
- Super admins need nothing further. Any non-super-admin role that should see or edit branding needs `branding.view` / `branding.manage` granted in Roles & Permissions — that remains an owner action.

## 23. Tab icon follows the uploaded logo (2026-11-21)

### 23.1 The gap

`app/layout.tsx` declared static `/icons/favicon.svg` and `/icons/favicon-64.png`, so the browser tab kept the Koperra mark no matter what Settings → Branding held; changing it meant shipping files.

### 23.2 Approach

- New `app/api/favicon/route.ts`, a dynamic route handler. Per request it reads `{API_URL}/api/branding`; when `logo_url` is set it fetches the blob and streams the bytes back with the blob's own content type and `Cache-Control: public, max-age=300`. With no logo, an unreachable backend, or a failed blob fetch it answers 307 to the static `/icons/favicon.svg` (60 s cache), so the tab is never blank.
- Layout metadata now declares `icon: [{ url: "/api/favicon" }]`. The apple touch icon stays `koperra-app-icon-1024.png` — iOS expects a 180 px PNG and caches it far more aggressively than desktop browsers do.
- The backend base URL is read from `NEXT_PUBLIC_API_URL`, which is available server-side, so no new environment variable was needed.

### 23.3 Verification

- Three route tests: streams the logo with its content type, redirects when no logo is set, redirects when the backend is unreachable. Focused run **3 passed**.
- `npx tsc --noEmit` clean; full Vitest **37 files / 250 tests**, with 2 failures — the documented jsdom flake (`login-redirects`, `BulkActionsBar`), both passing in isolation.
- `npm run build`: 21 static routes plus `/api/favicon` as a dynamic (ƒ) route.

### 23.4 Caveats

- Browsers cache tab icons beyond our headers; a newly uploaded logo may need a hard reload or a fresh tab before it shows.
- Each uncached request costs one function invocation and two upstream fetches; the 300 s browser cache keeps that rare.
- The iOS home-screen icon and `themeColor` remain static and still change only on deploy.

## 24. Branded print header and landing page (2026-11-21)

### 24.1 Print header

- `PrintableSchedule` carried its own `COOPERATIVE_NAME = "MACT Cooperative"` constant, so a deployment renamed in Settings still printed the old name. It now reads `useBranding()`: the heading and the `© … <year>` footer use `branding.cooperative_name`, and the uploaded logo renders above the heading at 48 px when one is configured (omitted otherwise, so the monogram-only deployments print unchanged).

### 24.2 Landing page

- `HomeView` hardcoded "MACT Cooperative Manager" in both states. The title is now `${branding.cooperative_name} Manager`, covering the signed-out landing page and the signed-in index, which is the one page outside the branded shells.

### 24.3 Navigation appearing in print

- Printing any admin page used to include the navy sidebar (fixed-position, so it repeated on every sheet) and the mobile top bar. `AdminNav.module.css` now hides `.topbar`, `.scrim` and `.sidebar` under `@media print`, and `AdminShell.module.css` drops the 264 px content offset in print, so reports use the full paper width. The printable schedule's own `.no-print` toolbar is unaffected.

### 24.4 Verification

- Focused tests: `PrintableSchedule` (now with the configured name, logo and footer) and `HomeView` (title from branding) — **10 passed**.
- `npx tsc --noEmit` clean; full Vitest **37 files / 252 tests passed**; `npm run build` unchanged at 21 static routes plus the dynamic `/api/favicon`.
- Print output itself is not observable in jsdom; the `@media print` rules still need a manual Ctrl+P check in the browser.

## 25. Notification backlog: staff producers, deduction and account notices, email preferences (2026-11-21)

### 25.1 What shipped

Section 21 shipped the member-facing notices; this slice closes the rest of the audit except the items listed in 25.6.

| Event | Recipient | Category | Title |
|---|---|---|---|
| Loan application submitted or re-applied | holders of `loan.review` | loan | New loan application |
| Payroll deduction confirmed | the member | contribution | Payroll deduction recorded |
| Payroll deduction marked not made | the member | contribution | Payroll deduction not made |
| Member login created | the member | account | Your login is ready |
| Password changed (self) | the member | account | Password changed |
| Password reset by an officer | the member | account | Your password was reset |
| Password reset from a recovery link | the member | account | Your password was reset |
| Admin account status changed | the admin | account | Account status changed |
| Admin password reset | the admin | account | Your password was reset |

- `notification_service.notify_staff(db, permission_code=..., ...)` fans a notice out to every active admin holding the permission, and returns how many were queued. Staff notices go to the officer who can act next (`loan.review` for a new application, i.e. payment verification), never to "all admins" — that would ping officers who cannot do anything with it.
- All notices are queued inside the business transaction. Bulk deduction actions write each notice inside that record's savepoint, so a record that rolls back takes its notice with it. Account-status changes commit inside `set_account_status`, so the notice is queued first; login creation uses `db.flush()` to obtain the new user id before notifying.

### 25.2 Email preferences (Phase G, minimal scope)

- New `notification_preferences` table: `user_id` PK (FK `users`, cascade), `email_loan`, `email_repayment` (both `BOOLEAN NOT NULL DEFAULT TRUE`), `updated_at`. Idempotent manual migration `scripts/manual_migration_2026_11_notification_preferences.sql`, registered in `ORDERED_MIGRATIONS`.
- `GET /api/notifications/preferences` answers `{email_loan, email_repayment}`, defaulting to `true/true` when the account has no row. `PUT` upserts the caller's row and applies only the fields present in the body. Both are hard-scoped to the token's user.
- `member_allows_email(db, member, category)` is the gate used before each member email send. Only `loan` and `repayment` are optional; `contribution`, `account` and `system` always send. Preferences live on the member's `role='member'` login while the email goes to `member.email`, so the gate resolves the login; a member with no login has no way to opt out, so their mail still sends.
- Gated send sites: form-payment rejection, application rejection, and disbursement. In-app notices are unaffected — an opt-out silences the email only.

### 25.3 Frontend

- `getNotificationPreferences` / `updateNotificationPreferences` in `lib/api/notifications.ts`.
- `components/dashboard/NotificationPreferences` — a card on the member dashboard with two checkboxes and an explicit **Save preferences** button. Save confirmation auto-clears after 4 s, and the copy states that in-app notices always show everything and that account and security emails cannot be turned off.

### 25.4 Email log wording

- `email_utils.py` previously logged one message for both 401 and 403. They are now distinct: 401 names a rejected API key, 403 names a sender/domain the key may not send from (the case that a mis-set `FROM_EMAIL` produces).

### 25.5 Verification

- Backend, focused (`tests/test_notifications.py`) **21 passed**; full suite on the sandbox test database **370 passed** (11 new).
- Frontend, focused (`NotificationPreferences` + `DashboardView`) **2 files / 5 tests passed**; `npx tsc --noEmit` clean; `npm run build` 21 static routes plus the dynamic `/api/favicon`.
- Full Vitest **38 files / 255 tests** reported 1 failure — the documented jsdom flake (`DeductionForm` queue prefill timing out), which passed **15/15** on an isolated rerun.
- Not browser-tested: signing in as a member requires entering credentials, which the standing constraint blocks, so the dashboard card was verified by component tests and the production build only.

### 25.6 Deliberately deferred

- **Web Push** — left for a future integration if the need appears.
- **Reminders, digest, outbox / scheduled delivery** — needs a scheduler the serverless deploy does not have.
- **Welcome / membership-approval emails** — the member lifecycle these hang off is not implemented.
- **Administrative-task-assigned and cooperative-announcement categories** — no underlying feature to attach them to.
- Security/account notices stay outside the preference system by design; adding switches for them would weaken the guarantee that a compromise is always reported.

### 25.7 Deploy

- Shipped as `761e5b3` and pushed to `main` 2026-11-21; both Vercel projects reported `success`. Production verified: `/api/health` 200, `/api/branding` 200, `/api/notifications` 401 and `/api/notifications/preferences` 401 (the 401 rather than 404 proves the new route is live), `https://koperra.sidgakstech.me/login` 200.
- `main.py` runs `Base.metadata.create_all()` at boot, so `notification_preferences` is created on the first backend deploy; the manual migration only keeps sandbox and Neon-branch parity.
- No new environment variables.

## 26. Loan interest deduction modes and a separately-paid processing fee (2026-11-22)

### 26.1 What shipped

- **The fee bug is fixed.** A loan type's `flat_charge` was being added to `total_repayable` and therefore to the instalment. It is a processing fee paid separately, so it is now outside every loan figure: `compute_loan_terms` no longer receives it, `Loan.fee_amount` snapshots what is owed at disbursement, and a new `loan_fee_payments` ledger records the member's payment and its verification. Verifying a fee changes nothing on the loan.
- **Interest can be recovered three ways**, configurable per cooperative, overridable per loan type and per rate version.

| Mode | Payout | Total repayable | Monthly instalment |
|---|---|---|---|
| `at_source` | principal − interest | principal | principal / tenure |
| `spread_over_tenure` | principal | principal + interest | (principal + interest) / tenure |
| `spread_first_months` (M months) | principal | principal + interest | principal / tenure, **plus** interest / M for the first M months |

- Existing disbursed loans are untouched. The migration defaults every existing row to `at_source` with `fee_amount = 0`, which reproduces what those loans already had.

### 26.2 Resolution order

A rate version may carry its own mode; otherwise the loan type's cached mode applies; otherwise the cooperative default in `settings.loan_interest_mode` applies. The spread months fall back independently (a type may set `spread_first_months` while inheriting the coop's month count). The loan snapshots `interest_mode`, `interest_spread_months` and `interest_installment` at disbursement, so later settings changes never rewrite an existing loan.

Validation: settings require a positive month count for `spread_first_months` and reject a stray month count for the other modes (merged-state check, 400). Disbursement raises `ValueError` when `spread_months > tenure_months` (possible after a later tenure change) and the router converts it to a 400 explaining the misconfiguration.

### 26.3 Arrears

One `monthly_installment` cannot express `spread_first_months`, so the deduction expectations engine asks `instalment_for_due_month(loan, n)` / `expected_total_by_due_month(loan, n)` instead: the first M instalments include `interest_installment`, later ones do not. `at_source` and `spread_over_tenure` behave exactly as before.

### 26.4 Fee payment endpoints (`backend/app/routers/loan_fees.py`)

| Endpoint | Who | Behaviour |
|---|---|---|
| `POST /api/loans/{id}/fee-payment` | the owning member | amount comes from `Loan.fee_amount`, never the client; refuses fee ≤ 0, an already-paid fee, or a duplicate awaiting review; notifies holders of `loan.fee_verify` |
| `GET /api/loans/{id}/fee-payments` | owner or `loan.view` | history for one loan |
| `GET /api/loan-fees?status=` | `loan.view` | cross-loan queue (`awaiting_verification`) or history |
| `GET /api/loan-fees/{id}` / `/receipt` | owner or `loan.view` | details / receipt |
| `POST /api/loan-fees/{id}/verify` | `loan.fee_verify` | row-locked, idempotent; COI guard returns 409; approve/reject notifies the member and writes `loan_fee.verified` / `loan_fee.rejected` audit events |

### 26.5 Schema, migration and permissions

- `scripts/manual_migration_2026_11_loan_interest_modes.sql` (idempotent): enums `interestdeductionmode` and `feepaymentstatus`; `settings.loan_interest_mode` (default `at_source`) + `loan_interest_spread_months`; the same nullable pair on `loan_types` and `loan_type_rate_versions`; `loans.interest_mode`, `interest_spread_months`, `interest_installment`, `fee_amount`; `loan_fee_payments` with status default `awaiting_verification` and indexes on status, loan and member; CHECK constraints for non-negative amounts and a positive spread period. Registered in `ORDERED_MIGRATIONS` with `apply_manual_migrations.py` server-default fixups.
- New permission `loan.fee_verify` ("Verify/reject a separately-paid loan fee payment"), granted by default to Loan Officer and Treasurer (Super Admin is automatic).

### 26.6 Frontend

- `lib/loanMath.ts` mirrors the backend so the four previews (admin disbursement, member application, types manager, dashboard) cannot drift; previews now state the mode, show the fee as owed separately, and show the first-M-months interest portion.
- Types manager lists each type's mode (or "Cooperative default") and accepts a mode + months when adding a type; the rate-history panel does the same per version and shows the mode in history.
- Admin settings gained the cooperative-default mode and month count; they are saved in the configuration scope alongside the other module settings.
- Member dashboard: a "Processing fee" column with its state (due / awaiting verification / rejected + reason / paid) and a Pay/Resubmit fee form that uploads the receipt.
- New `/admin/loan-fees` review page (`components/loan-fees/`): awaiting-verification queue with an all-history filter, receipt preview, rejection reason, conflicted rows read-only; added to the Loan Management menu when the officer holds `loan.fee_verify`.

### 26.7 Verification

- Backend: `tests/test_loan_interest_modes.py` (10) and `tests/test_loan_fees.py` (10) — **20 passed**; full suite on the sandbox test database **390 passed**. The sandbox `mact_test` and `mact_local` databases had the new migration applied.
- Frontend: `npx tsc --noEmit` clean; `npm run build` produced 23 static routes including `/admin/loan-fees`; new component tests (`FeePaymentsTable` 3, `LoansSection` 4) and the rewritten `computeDisbursePreview` tests (6) passed. Full Vitest **40 files / 265 tests** reported 1 failure — the known jsdom timeout flake, this time in `ContributionReviewPanel`, which passed **3/3** on an isolated rerun.
- The local backend and frontend both booted (frontend 200). **Authenticated browser checks were not run**: signing in requires entering credentials, which the standing constraint blocks — the fee UI is covered by the component tests and the production build only.

### 26.8 Deploy

- Before deploying, run `manual_migration_2026_11_loan_interest_modes.sql` on the production branch (the app's `create_all` creates `loan_fee_payments` but cannot add the columns), then run `scripts/seed_permissions.py` so `loan.fee_verify` exists and can be granted; existing roles keep their customizations, so assign it to Loan Officer/Treasurer where the defaults are wanted.
- No new environment variables.
- Shipped and deployed 2026-11-22 as `b2fc4bb`, pushed with the cancellation notice (`6409309..9be33c4`). Production branch `br-rough-flower-aycl78im` received the migration before the push — the runner reported `[REMOTE (ep-rapid-feather-ay5ak2pz…)]`, applied `manual_migration_2026_11_loan_interest_modes.sql`, and restored the new server defaults; `seed_permissions.py` then seeded/updated 44 permissions.
- Both Vercel contexts reported `success`. Verified after deploy: `/api/health` 200, `/api/branding` 200 (proves the new settings columns are readable), `/api/settings` 401, `/api/notifications` 401, and `/openapi.json` exposes `/api/loan-fees`, `/api/loan-fees/{payment_id}`, `/api/loan-fees/{payment_id}/receipt` and `/api/loan-fees/{payment_id}/verify`, each 401 unauthenticated; frontend `/` and `/login` 200.
- The seed never touches existing roles, so **`loan.fee_verify` exists in production but is not yet granted to Loan Officer or Treasurer** — assign it on `/admin/roles` where the default is wanted.

## 27. Member cancellation notifies the reviewers (2026-11-22)

### 27.1 The gap

Submitting an application told the `loan.review` holders, but cancelling one told nobody: `POST /api/loan-applications/{id}/cancel` changed the status and wrote a `loan_application.cancelled` audit row only. An approved-but-undisbursed application that the member cancels disappears from the disbursement queue without any signal, which is exactly the case an officer needs to know about.

### 27.2 Implementation

- `cancel_application` now calls `notification_service.notify_staff(db, permission_code="loan.review", ...)` before the commit, so the notice is queued in the same transaction as the status change — same contract as the submission notice.
- Recipients are limited to active admins holding `loan.review`; officers with only `loan.view` or `disbursement.*` are not pinged, and the member who cancelled gets no notice for their own deliberate action.
- Notice: category `loan`, title **Loan application cancelled**, body naming the member, loan type and amount (`approved_amount`, falling back to `requested_amount` for still-pending applications) plus a reminder that the loan-form fee is not refunded, link `/admin/loan-applications`.

### 27.3 Verification

- `tests/test_notifications.py` — 2 new tests: a reviewer receives exactly one notice with the right title/amount/link while the member receives none, and an admin holding only `loan.view` receives nothing. Focused run **23 passed**; full backend suite **392 passed**.
- Full Vitest run was **39/40 files, 264/265 tests** — the one failure was the documented jsdom/CPU-contention flake in `NotificationBell` (unread-count test), which passed **8/8** on an isolated rerun.

### 27.4 Deploy

- No schema change and no new permission. Shipped as `9be33c4` in the same deploy as section 26 (2026-11-22), whose production migration and permission seed ran before the push; both Vercel contexts reported `success`.

## 28. Cooperative policy settings foundation (2026-11-23)

### 28.1 What moved out of code

Two payroll policies were constants: a 5,000 monthly contribution floor and a loan default charge percentage that had no value at all. Both now live on the single `settings` row, so one deployment can serve cooperatives with different policies:

| Setting | Meaning | Default |
|---|---|---|
| `minimum_monthly_contribution` | Floor for a member's monthly contribution; 0 means no floor | backfilled to the old 5,000 floor |
| `default_monthly_contribution` | Figure offered when recording an amount | 0 |
| `loan_default_charge_pct` | Charge raised once per missed instalment | 0 |
| `loan_default_grace_mode` | `next_payroll` or `days` | `next_payroll` |
| `loan_default_grace_days` | Day count for the `days` mode, 0–365 (CHECK constraint) | 0 |

### 28.2 Where the floor is enforced

`backend/app/cooperative_settings.py` reads the row per request (no caching — a policy change applies to the very next request). The floor is checked where the session exists: member create and update, the contribution-change request, and the approval path, so a floor raised while a request sat in review is re-checked before the approved amount is committed.

### 28.3 Migration

`manual_migration_2026_11_cooperative_policies.sql` (idempotent) adds the five columns with CHECK constraints and backfills existing rows to the old 5,000 floor; fresh databases get neutral server defaults (see `SERVER_DEFAULT_FIXUPS` in `apply_manual_migrations.py`).

### 28.4 Frontend

- `ContributionSettingsSection` and `LoanDefaultSettingsSection` in the admin Settings screen; the settings type, scopes, and dirty-state handling were extended alongside them.
- The dashboard contribution card and the member form consume the default figure instead of a hard-coded value.

### 28.5 Verification and deploy

- `tests/test_cooperative_policies.py` — 6 tests covering floor enforcement on every path and the merged grace-mode validation; full backend suite green at the time.
- Committed as `6fe8edd` and pushed. No new permission and no environment variable.
- **Correction (2026-11-23):** the migration was not applied to the production branch when that push deployed, so the settings row lacked the five new columns and every read of it failed — `/api/branding` returned **500** from 2026-11-23 until the ordered runner was applied to `br-rough-flower-aycl78im` during the section 29 deploy. `/api/branding` returned 200 immediately after.

## 29. Member savings ledger and exit settlement (2026-11-23)

Step 2 of the accounting rebuild. Built on standing double-entry principles, not the workbook's shortcuts: savings is a liability the cooperative owes the member, kept on its own append-only subledger.

### 29.1 The ledger

`savings_entries` is append-only and typed: `contribution`, `contribution_reversal`, `exit_offset`, `exit_payout`. The balance is the sum of the entries (credits minus debits); nothing is edited or deleted, so a confirmed payroll month that is later voided gets a reversal entry instead — enforced by the unique `(deduction_line_id, entry_type)` constraint. Confirmed `monthly_contribution` deduction lines post their entries from the payroll confirm path, and the migration backfills the entries for months confirmed before the ledger existed.

### 29.2 Exit settlement

`member_settlements` holds one snapshot row per member (`UNIQUE member_id`); `settlement_allocations` records how much of the settlement went to each loan. The figures are snapshots of the moment of settlement and are never recomputed, so a later payroll correction cannot rewrite what the office settled.

`backend/app/settlements.py`:

- **Guards before anything is written**: the member must have a recorded exit date (409), must not already be settled (409), must not have a live DRAFT/SUBMITTED deduction (409 — the payroll queue and the settlement would otherwise both consume the same savings), the settlement date may not be in the future (400), the ledger balance may not be negative (409), and there must be something to settle (400).
- **Order of application**: savings offset active loans oldest first (disbursement date, then id), crediting `amount_repaid` and completing fully-repaid loans; the remainder becomes `payout_amount`. Zero payout is recorded as already `paid` at settlement; anything else starts `pending`.
- **Ledger entries at settlement**: `exit_offset` for what went to loans and `exit_payout` for the money handed back — the ledger is debited in full at settlement, so the member's savings balance closes even while the payout is still owed.
- **Mark paid** records `paid_on`, `paid_at` and a mandatory bank/cash reference (whitespace collapsed); it cannot precede the settlement date or be in the future, and repeats are refused (409).

### 29.3 Endpoints and permissions

| Endpoint | Permission | Behaviour |
|---|---|---|
| `GET /api/members/{id}/settlement` | `savings.view` | Preview: current savings balance, active loan count and outstanding, plus any recorded settlement |
| `POST /api/members/{id}/settle-exit` | `savings.settle` | Row-locks the member, runs the COI guard, calls `settlements.settle`, audits `member.exit_settled` |
| `POST /api/members/{id}/settlements/mark-paid` | `savings.settle` | Row-locks the settlement row, COI guard, audits `member.exit_payout_paid` |

`settlements.settle` notifies the member in the same transaction as the state change; audits are written after the commit, following the established ordering. `delete_member` now counts an existing settlement as financial history, alongside loans and applications. The deduction-expectations engine excludes settled members, so a residual loan balance can never re-enter the payroll queue after the books are closed.

### 29.4 Frontend

`MemberSettlementPanel` sits in the member details modal, only for members with a recorded exit and only with `savings.view`:

- Unsettled: savings available and loans outstanding, then an inline settle form (date defaulting to today, optional note, explanation that savings offset loans oldest first and the remainder is owed as a payout).
- Settled: date, savings at settlement, amount applied, payout, status, and — when pending — an inline mark-paid form (date bounded between the settlement date and today, required reference that enables the button). Pending-payout view-only officers get explanatory copy instead of the form.
- `useMembersPage` exposes `savings.canView` / `savings.canSettle` from the user's permissions; conflicted officers see the panel read-only.

### 29.5 Sandbox fixture

`scripts/seed_local_sample_data.py` gained a self-resetting fixture (`QLEXIT`): a non-financial member with an exit date, 12,000 of contributions on the ledger and an 8,000 Capital Loan still open. Re-running the seed deletes any settlement recorded while exercising the flow (cascading to its allocations and ledger entries), restores the loan to ACTIVE with nothing repaid, and normalizes the contribution, so the member is always back at the start of the two-step demo.

### 29.6 Verification

- Backend: `tests/test_savings_settlement.py` — **14 passed** (guards, oldest-first allocation across two loan types, ledger postings, preview before/after, mark-paid validation, settled member refused by payroll creation, residual loan leaving the queue, permissions, audit events); full suite **412 passed**.
- Frontend: full Vitest **273 passed**; `npx tsc --noEmit` clean.
- Live browser check (2026-11-23): because the running `:8000` backend predates this code and could not be restarted, an isolated copy of the UI was served on `:3010` against a temporary backend on `:8020` (origin added to CORS); the user's own servers were left untouched. Verified end to end as `localadmin`: details modal showed 12,000 savings vs 8,000 outstanding; settling posted offset 8,000 with payout 4,000 **Pending** and allocation "Capital Loan 8,000"; the mark-paid form refused an empty reference, then recorded **Paid**, paid-on 2026-11-23, reference "CASH 0421". The zero-payout path was also exercised earlier (payout 0 settles directly as Paid).

### 29.7 Deploy

- Shipped as `40375a3` on 2026-11-23. Before the push, the ordered runner (`scripts/apply_manual_migrations.py --allow-remote`) was applied to production branch `br-rough-flower-aycl78im` (host `ep-rapid-feather-ay5ak2pz…`): 22 files applied, 1 already applied, server defaults restored. That run also applied `manual_migration_2026_11_cooperative_policies.sql`, which had been missed after `6fe8edd` — `/api/branding` went from 500 to 200 immediately.
- The same branch then ran `scripts/seed_permissions.py`; all five roles already existed and kept their grants. `savings.settle` now exists in production but is **not yet granted** — assign it to Treasurer (and any other officer who settles exits) on `/admin/roles`, since the seeder never rewrites an existing role.
- No new environment variables. Verified after deploy: `/api/health` 200, `/api/branding` 200, `/api/members/{member_id}/settlement` 401 unauthenticated, `/openapi.json` exposes `/api/members/{member_id}/settlement` and `/api/members/{member_id}/settlements/mark-paid`, frontend `/` 200.
