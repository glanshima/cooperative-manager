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
   (approve with a possibly-different amount, or reject). Approval creates
   an actual `Loan` record and emails the member the full terms via Resend.
   A member flagged `loan_restricted` is either blocked or flagged for
   admin attention on submission, per an admin-configurable setting.
5. **Settings** — single-row table: loan-restriction behavior (block/warn),
   loan form fee amount, and per-module enable/disable toggles (not yet
   enforced on the frontend nav — see Next steps).

### IMPORTANT — before redeploying: run a manual DB migration

`scripts/manual_migration_2026_08_add_loan_application_columns.sql` adds
new columns to your **existing** `members` and `loan_types` tables. The
app's `create_all()` only creates missing tables automatically (so the new
`users`, `loan_applications`, and `settings` tables appear on their own) —
it does **not** add missing columns to tables that already have data.
Run that SQL file in Neon's SQL Editor once, before your next backend
deploy, or requests touching the new fields will fail.

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
