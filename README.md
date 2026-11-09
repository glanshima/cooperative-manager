# MACT Cooperative Manager

© SIDGAKS Tech

Web app replacement for the legacy Excel-based cooperative ledger.
Built module by module end-to-end (DB → API → UI): members, loans, loan
applications, repayments, disbursements, and month-end payroll deductions.
Cashbook and dividends follow the same pattern.

## Structure

```
mact-app/
├── backend/          FastAPI app (Python)
│   └── app/
│       ├── main.py          entrypoint
│       ├── database.py      SQLAlchemy engine/session
│       ├── models.py        ORM models
│       ├── schemas.py       Pydantic request/response schemas
│       └── routers/
│           └── members.py   Members CRUD endpoints
├── frontend/          Next.js app (TypeScript)
│   ├── app/
│   │   ├── page.tsx
│   │   └── members/page.tsx  Members list + form
│   └── lib/api.ts            typed API client
└── scripts/
    └── migrate_members_from_xlsx.py   pulls membersTable out of the old workbook
```

## 1. Database (Neon)

1. Create a free project at https://neon.tech.
2. Copy the connection string it gives you.
3. Enable the `pgcrypto` extension once (needed for `gen_random_uuid()` used
   by the migration script):
   ```sql
   CREATE EXTENSION IF NOT EXISTS pgcrypto;
   ```

## 2. Backend

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in DATABASE_URL from Neon
uvicorn app.main:app --reload --port 8000
```

Visit http://localhost:8000/api/health to confirm it's running. The first
request also creates the `members` table automatically.

## 3. Migrate existing member data (optional)

```bash
export DATABASE_URL=postgresql://...   # same value as in backend/.env
cd scripts
pip install openpyxl sqlalchemy psycopg2-binary
python migrate_members_from_xlsx.py /path/to/MACT_COOPERATIVE_AUTOMATED_LEDGER.xlsx
```

## 3b. Seed loan types / migrate historical loans (optional)

```bash
export DATABASE_URL=postgresql://...
cd scripts
python migrate_loans_from_xlsx.py /path/to/MACT_COOPERATIVE_AUTOMATED_LEDGER.xlsx
```
Safe to re-run any time — seeds the 5 loan products from the workbook and
picks up any historical disbursements without creating duplicates.

## 4. Frontend

```bash
cd frontend
npm install
cp .env.local.example .env.local   # points to http://localhost:8000
npm run dev
```

Visit http://localhost:3000/members.

Tests (Vitest + React Testing Library, colocated as
`components/**/index.test.tsx`): `npx vitest run --pool=forks` — the
forks pool avoids an intermittent worker-thread OOM on Windows. Type
check with `npx tsc --noEmit`. See
[LOCAL_TESTING_AND_PRE_PUSH.md](./LOCAL_TESTING_AND_PRE_PUSH.md) Gate 3.

## 5. Deploy (Vercel)

See **[DEPLOYMENT.md](./DEPLOYMENT.md)** for the full step-by-step guide
(Neon setup, GitHub push, both Vercel projects, CORS wiring, data
migration, and a troubleshooting table). Short version:

- Import `frontend/` as one Vercel project (framework preset: Next.js).
- Import `backend/` as a second Vercel project (framework preset: FastAPI /
  Python runtime). Set `DATABASE_URL`, `ALLOWED_ORIGINS`, and `SECRET_KEY`
  as environment variables in the Vercel dashboard.
- Set the frontend's `NEXT_PUBLIC_API_URL` env var to the deployed backend URL.

## Modules built so far

1. **Members** — full CRUD, migrated from `membersTable` (191 real members).
   Now includes `loan_restricted` / `restriction_reason` (admin-set manual
   flag, not a salary calculation) and admin-provisioned member logins.
2. **Loans** — `loan_types` (rate + tenure + flat charge + open-for-application
   toggle) and `loans` (one row per disbursement). A member may hold
   several active loans at once as long as they are of **different loan
   types**; a second active loan of the same type is rejected (409) by
   every activation path (direct create, status update, application
   disbursement, and deduction-void reopen). A partial unique index
   (`uq_loans_member_loan_type_active`) enforces the same rule in the
   database for concurrent requests. Interest = principal × rate, total
   repayable = principal + interest + flat charge, monthly installment =
   total repayable / tenure. See earlier notes on the "CR R&O" workbook
   inconsistency and the confirmed-zero historical loan data finding.
3. **Auth** — `users` table, PSN-based login for members (admin-provisioned,
   temporary password, forced reset on first login), separate admin
   accounts, JWT sessions. No self-registration by design.
4. **Loan Applications (member self-service)** — members apply for
   loan types an admin has flagged "open for application," pay a fixed
   loan-form fee by bank transfer, and upload a receipt (stored as base64
   in Postgres — see the cost/tradeoff note further down). An admin
   verifies the payment, then separately decides the loan itself
   (approve with a possibly-different amount and/or tenure, or reject).
   Approving does NOT disburse — see #7 below. A member flagged
   `loan_restricted` is either blocked or flagged for admin attention on
   submission, per an admin-configurable setting.
5. **Settings** — single-row table: loan-restriction behavior (block/warn),
   loan form fee amount, and per-module enable/disable toggles. Toggles are
   enforced in both the UI (nav links + `ModuleGate` on gated routes) and
   the API (`require_module_enabled` returns 403 for a disabled module).
6. **Interest-at-source loan model** — confirmed with MACT: interest is
   deducted from what's disbursed (`net_disbursed = principal -
   interest_amount`), not added on top of what's repaid
   (`total_repayable = principal + flat_charge` only — flat charges are a
   separate processing fee and are NOT "at source"). Fixes the "why is
   the balance 990,000 on a 900,000 loan" issue flagged during testing.
7. **Effective-dated loan type rates** — editing a loan type's rate,
   tenure, or flat charge no longer overwrites it in place. Instead it
   creates a new `LoanTypeRateVersion` row with an admin-chosen
   `effective_from` date (can be past, today, or scheduled in the
   future). Any new loan (direct disbursement or application decision)
   looks up whichever version was effective as of the relevant date.
   Loans already disbursed store their own computed numbers permanently
   and are never affected by later rate changes — this falls out of the
   existing design for free, no extra code needed to enforce it.
8. **Tenure negotiation** — a member may request a tenure shorter than
   or equal to a loan type's default when applying. An admin sets
   `approved_tenure_months` at decision time (may differ from the
   request, with `tenure_decision_reason` explaining why); repayment math
   always uses the approved tenure.
9. **Disbursement preferences + gated activation** — a member states a
   preferred disbursement date (informational only) and can choose to
   receive funds at an alternate account for that one loan instead of
   their account on file. Approving an application no longer creates a
   `Loan` — a separate, explicit **"Disburse"** admin action does that,
   normalizing `disbursement_date` to the 1st of the month it's actually
   disbursed in. This is the only point a detailed email fires (approval
   itself doesn't email — the member already sees "approved" on their
   dashboard).
10. **Loan servicing (member-initiated repayments)** — a member on an
    active loan can submit a repayment claim with a bank reference and
    receipt, mirroring the same payment-proof pattern as loan
    applications. An admin verifies it before it actually increases
    `Loan.amount_repaid`; the loan auto-completes once fully repaid.
11. **Next of kin expansion** — `Member` now also has
    `next_of_kin_address`, `next_of_kin_email`, and
    `next_of_kin_relationship` alongside the existing name/phone fields.
12. **Payroll deductions** — month-end staff deductions keyed by member +
    payroll month. A record holds monthly-contribution lines, explicit
    per-loan repayment lines, and free-form "other" lines. Lifecycle is
    append-only: `draft → submitted → confirmed`, plus `not deducted`
    (payroll omitted it; member pays by bank/cash and the existing
    receipt/evidence repayment flow applies) and `void` (reverses applied
    loan credits and reopens any loan a confirmed record completed).
    Loan balances change **only on confirmation**, never on entry or
    submission. Duplicate active records per member/month are blocked by
    a partial unique index. Admins can act per record or in bulk, and
    print a monthly schedule with contribution/loan/other/total columns
    (`/admin/deductions`). Permissions: `deduction.view/create/submit/
    confirm/void`; seeded roles get them via `seed_permissions.py`, but
    **existing custom roles are not updated automatically** — grant the
    new permissions to any existing Treasurer/Loan Officer/Auditor roles
    you rely on.
13. **Monthly contribution amounts + change requests** — a member's
    agreed amount lives on the member record (`monthly_contribution_amount`,
    `contribution_effective_from`, minimum ₦5,000) and is **never edited
    directly** once on file: members request a change from their dashboard
    and officers file one on behalf from the Members page; an admin
    approves or rejects (rejection requires a reason). Approved amounts
    apply from the 1st of the following month, never retroactively. At
    most one *pending* request per member (unique index). The deduction
    Enter tab (`/admin/deductions`) consumes this: `GET
    /api/payroll-deductions/worklist` returns the month's queue — who is
    due (contribution and/or instalments), each member's expected lines
    and totals, warnings (e.g. no amount on file), and who is already
    entered — so entry is one click per member with amounts pre-filled;
    overriding an expectation is what the conflict-of-interest guard
    treats as discretionary.

### IMPORTANT — before redeploying: run the manual DB migrations, in order

Use the ordered runner rather than applying files by hand:

```bash
# local sandbox (defaults to backend/.env)
backend/.venv/Scripts/python.exe scripts/apply_manual_migrations.py

# a Neon branch / other disposable DB
DATABASE_URL="postgresql://...branch..." \
  backend/.venv/Scripts/python.exe scripts/apply_manual_migrations.py --allow-remote
```

The runner calls `create_all()` first (so genuinely new tables appear)
and then applies every file in `ORDERED_MIGRATIONS`, ending with
`manual_migration_2026_11_contribution_amounts.sql` — the
contribution-amount feature: nullable `members.monthly_contribution_amount`
/`contribution_effective_from`, the `contribution_change_requests` table
(+ its status enum and "one pending request per member" unique index),
`payroll_deduction_lines.expected_amount`, and
`loan_repayments.payment_month`. Before it runs
`manual_migration_2026_11_membership_exit.sql` — two nullable columns,
`members.membership_exit_date` and `membership_exit_reason`, which record
that a member formally left the cooperative (see the withdrawal
endpoint). Nullable means existing rows are untouched: they simply have
no recorded exit. Before that runs
`manual_migration_2026_11_unique_active_loan_type.sql`, which
pre-checks for members who already hold more than one active loan of the
same type and aborts with the offending member/loan IDs if any are
found — close those loans first, then re-run. It then creates the
partial unique index `uq_loans_member_loan_type_active`.
`manual_migration_2026_11_payroll_deductions.sql` (new enums, both
deduction tables, the deduction-month unique index, and the month index)
runs just before it. Every file is idempotent, so re-running is safe.
Tables like
`loan_type_rate_versions` and `loan_repayments` are created by
`create_all()` on first deploy — no separate manual step.

**Known gap, not fixed by the migration:** if you already have a real
disbursed loan from before this session (e.g. a test 900,000 Capital
Loan), its `total_repayable`/`monthly_installment` were computed under
the OLD (incorrect) formula and are **not** automatically recalculated —
the migration only adds columns and backfills `net_disbursed = principal`
for historical rows. Decide separately whether to correct or delete/redo
that specific loan now that the calculation is fixed.

### Bootstrapping the first admin account

There's no signup flow. Run this once, locally, against your Neon DB:
```bash
export DATABASE_URL=postgresql://...
export SECRET_KEY=...                 # same value as backend/.env
cd scripts
pip install sqlalchemy psycopg2-binary passlib[bcrypt]
python create_admin.py <username> <password>
```

### Email (Resend)

Set `RESEND_API_KEY` and `FROM_EMAIL` in the backend's environment
variables (see `.env.example`). If either is missing, `email_utils.py`
logs a warning and skips sending rather than crashing a successful loan
decision — so it's safe to leave unset while you're still testing other
parts of the flow.

### bcrypt/passlib compatibility (already fixed, noted for reference)

`backend/requirements.txt` pins `bcrypt==4.0.1` explicitly alongside
`passlib[bcrypt]==1.7.4`. Without this pin, pip installs the newest
bcrypt (5.x), which breaks passlib's internal self-test with `ValueError:
password cannot be longer than 72 bytes` on literally any password,
including short ones — the error is misleading, it's not about your
actual password length. If you ever bump these dependencies, keep them
pinned together or re-verify compatibility first.

### New pages this session
- `/admin/loan-repayments` — admin review queue for member-submitted
  repayment receipts (separate from `/admin/loan-applications`)
- Loan type manager (`/loans`) now has a "Rate history" view per type
  instead of directly editable rate/tenure/flat-charge fields

### Auth model quick reference
- Members log in with their **PSN** as the username.
- Admin creates a member's login (Members page → "Create login") with a
  temporary password; the member is forced to change it via
  `/change-password` before reaching anything else.
- `GET /api/settings` is readable by any authenticated user (members need
  to see the loan form fee); only admins can update it.
- Members can only see/act on their own records (`/api/members/me`,
  their own loans, their own applications); admins see everything.

## Round 1 (flagged items batch) — small, isolated fixes

- Members search box now refreshes correctly when cleared (fixed a
  React-closure bug where the fix itself could have reintroduced the
  same class of bug — `refresh()` now takes an explicit search override).
- Loan types have a `description` field.
- Member's dashboard application form shows a live "estimated terms"
  calculator as they fill it in.
- Rejected applications show the specific rejection reason directly on
  the member's dashboard.

### Migration: `scripts/manual_migration_2026_08_round1_description.sql`

## Round 2 (flagged items batch) — schema/logic changes

- **Balance deduction at disbursement** — when disbursing a loan to a
  member with existing active loan(s), an admin can select specific
  loans (or "deduct all") to fully close out against the new
  disbursement. Deduction is always full payoff, never partial —
  selected loans get `amount_repaid = total_repayable` and flip to
  `COMPLETED`. The new loan's own principal/interest/repayment schedule
  are unaffected; only `net_disbursed` (the actual payout) shrinks by
  the deducted total. If the deduction would exceed `net_disbursed`, the
  disbursement is rejected with a clear error rather than going negative.
- **Structured alternate account** — `alternate_account_number` (single
  field) became `alternate_bank_name` / `alternate_account_name` /
  `alternate_account_number` on applications, and the equivalent
  `disbursement_*` trio on `Loan` (snapshotted at actual disbursement).
- **Dedicated disbursement list** — `/admin/disbursements`: a real
  filterable (loan type, approval date range) list of every approved,
  undisbursed loan, with the balance-deduction picker built into the
  disburse action. The original one-at-a-time disburse button inside
  `/admin/loan-applications`'s review panel still works too (no
  deduction UI there — use the dedicated page when deduction matters).
- **Cancel / reschedule** — a member can cancel (forfeits the loan-form
  fee, no refund) or reschedule (just updates the preferred date, no fee
  impact) any application that hasn't been disbursed yet — i.e. still
  `PENDING`, or `APPROVED` but not yet disbursed. New `CANCELLED` status
  value.
- **Reapply** — when an admin rejects a loan *decision* (not a payment
  rejection — those can't be reapplied without a fresh application
  regardless), they set `can_reapply` (defaults to `True`, so it's a
  single checkbox to *uncheck* only for genuine non-qualification cases,
  not extra friction for the common fixable-mistake case). A member can
  then submit a fresh application referencing the rejected one, with a
  brand-new payment (the old one was already consumed).

### Migration: `scripts/manual_migration_2026_08_round2.sql`

This one includes a `DO $$ ... ALTER TYPE ... ADD VALUE 'cancelled' $$`
block to add the new enum value to Postgres — the migration comments
explain how to verify the enum type's actual name if it doesn't match
`loanapplicationstatus` (SQLAlchemy's default naming convention, used
here since no explicit `name=` was set on that column).

## Next steps

- **Bulk / Excel deduction entry** — deductions currently support
  per-member entry, bulk lifecycle actions, and a printable schedule;
  spreadsheet import/export is the natural next step.
- **Cashbook & financial statements** — signed transaction amounts,
  aggregated into income/expenditure and assets/liabilities views.
- **Dividends** — reserve %, honorarium %, member payout % applied to net
  income, per the `CashBook` sheet's W3:W5 percentages.
- **Deferred from the flagged-items list** (bigger, self-contained units):
  batch Excel upload/download, member self-service profile (photo,
  password) with restricted-field editing, member detail panel with
  revoke-login.
- **UI polish pass** — deferred by design until all modules exist (see
  conversation history); current pages are functional but not styled for
  mobile.
