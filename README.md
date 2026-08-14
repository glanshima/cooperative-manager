# MACT Cooperative Ledger

Web app replacement for the legacy Excel-based cooperative ledger.
This scaffold covers the **Members module** end-to-end (DB → API → UI) as
the first vertical slice. Loans, deductions, cashbook, and dividends follow
the same pattern module by module.

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
   toggle) and `loans` (one row per disbursement). Interest = principal ×
   rate, total repayable = principal + interest + flat charge, monthly
   installment = total repayable / tenure. See earlier notes on the
   "CR R&O" workbook inconsistency and the confirmed-zero historical loan
   data finding.
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
   loan form fee amount, and per-module enable/disable toggles (not yet
   enforced on the frontend nav — see Next steps).
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

### IMPORTANT — before redeploying: run TWO manual DB migrations, in order

1. `scripts/manual_migration_2026_08_add_loan_application_columns.sql`
   (from the previous session, if not already run)
2. `scripts/manual_migration_2026_08_loan_features_batch2.sql` (this
   session) — adds next-of-kin columns, `net_disbursed` +
   `disbursement_account_number` on `loans` (with a backfill for any
   existing loan rows), and the tenure/disbursement-preference columns
   on `loan_applications`. New tables (`loan_type_rate_versions`,
   `loan_repayments`) are created automatically by `create_all()` on
   first deploy — no manual step needed for those.

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

## Next steps

- **Enforce the module enable/disable toggles** — `Settings` stores them,
  but nothing currently hides a disabled module's nav links or blocks its
  API routes. Worth doing before relying on them.
- **Deductions / transactions module** — replaces the 59 monthly deduction
  tables with one time-series table filtered by date range.
- **Cashbook & financial statements** — signed transaction amounts,
  aggregated into income/expenditure and assets/liabilities views.
- **Dividends** — reserve %, honorarium %, member payout % applied to net
  income, per the `CashBook` sheet's W3:W5 percentages.
- **UI polish pass** — deferred by design until all modules exist (see
  conversation history); current pages are functional but not styled for
  mobile.
