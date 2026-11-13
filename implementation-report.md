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

## 7. Build and test results

### Next.js production build

```
▲ Next.js 16.4.6 (Turbopack)
✓ Compiled successfully
✓ Running TypeScript … no errors
✓ Generating static pages (20/20)

/admin/dashboard  ○  static — build succeeded
```

### Frontend tests (Vitest, 24/24 passed)

```
✓ app/login/login-redirects.test.tsx (4 tests)
    ✓ redirects to /change-password when must_change_password is true
    ✓ redirects to /admin/dashboard for an admin who has already changed their password
    ✓ redirects to /dashboard for a member who has already changed their password
    ✓ shows an error message and does not redirect when login fails

✓ components/admin-dashboard/AdminDashboardView/index.test.tsx (12 tests)
  AdminDashboardView (5)
    ✓ renders the heading and the signed-in username
    ✓ shows all navigation links when every module is enabled
    ✓ hides module-gated links when every module is disabled
    ✓ renders each nav link with the correct href
    ✓ shows the settings error banner when settings failed to load
  useAdminDashboardPage (7)
    ✓ does not fetch while auth is still loading
    ✓ does not fetch when user is null (unauthenticated)
    ✓ calls getSettings (and only getSettings) once auth resolves
    ✓ exposes correct module flags when all modules are on
    ✓ exposes correct module flags when all modules are off
    ✓ surfaces a settingsError and clears loading when getSettings rejects
    ✓ re-fetches when auth transitions from loading to resolved

✓ components/dashboard/hooks/useDashboardPage.test.ts (4 tests)
    ✓ loads loan data when the Loans module is enabled
    ✓ skips every loan request when the Loans module is disabled
    ✓ sends the month the member says they paid, not today's month
    ✓ refuses to submit without a payment month

✓ components/home/HomeView/index.test.tsx (4 tests)
    ✓ shows only the login link when signed out
    ✓ shows admin pages but hides disabled modules
    ✓ shows the deductions link to admins while the module is enabled
    ✓ shows a member only their dashboard and enabled modules
```

Date: 2026-11-14
