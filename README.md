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

## Next modules to build (same pattern each time)

1. **Loan types & loan disbursement** — mirrors `Loan Types` and
   `Loan Disbursement` sheets; interest = principal × rate, repayment =
   principal / tenure.
2. **Deductions / transactions** — replaces the 59 monthly deduction tables
   with one time-series table filtered by date range.
3. **Cashbook & financial statements** — signed transaction amounts,
   aggregated into income/expenditure and assets/liabilities views.
4. **Dividends** — reserve %, honorarium %, member payout % applied to net
   income, per the `CashBook` sheet's W3:W5 percentages.
