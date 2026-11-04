# Local Testing & Pre-Push Checklist

How to test changes **offline** against a disposable local sandbox, verify
them against a throwaway Neon branch, and only then push code to `main`.

**The rule that matters:** sample data (fake members, logins, loan types,
loans) lives only on your machine, under `.local/` (gitignored). It is
never pushed, never seeded into Neon, never deployed. Only **code** and
**schema-only migrations** travel to git / Neon / Vercel.

---

## 1. The pieces

| Piece | What it is | Where |
|---|---|---|
| `scripts/local_db.py` | An embedded PostgreSQL (via the `pgserver` pip package) that runs **only on 127.0.0.1:55432**, with trust auth. Creates the `mact_local` (seeded sample data) and `mact_test` (pytest) databases. All state in `.local/` (gitignored). | `start` / `stop` / `status` / `url` / `psql` / `reset --yes` |
| `scripts/apply_manual_migrations.py` | Applies `scripts/manual_migration_*.sql` in a fixed dependency order, in one pass, idempotently (re-runs are safe). Sandbox by default (reads `backend/.env`); a Neon **branch** requires `--allow-remote`. Never writes sample data — schema only. | repo root |
| `scripts/seed_local_sample_data.py` | Creates the sample admin/members/logins/loan types described below. **Refuses to run** unless `DATABASE_URL` points at `127.0.0.1:55432` — this guard is deliberate; do not bypass it. Idempotent (safe to re-run). | repo root |
| `backend/tests/` | The pytest suite. Needs a real Postgres via `DATABASE_URL`; runs per-test rollback, but still truncates/creates freely — always point it at `mact_test`, never at real data. | `backend/` |
| `scripts/smoke_test.py` | 8-step end-to-end check over real HTTP against a running backend (health → admin login → member lookup → loan types → member login → member self → submit application → read back). **Step 7 creates a real loan-application row** in the target database. | repo root |

## 2. One-time setup

```bash
# Backend deps (incl. pgserver for the sandbox) into the repo's venv
python -m venv backend/.venv                       # skip if it already exists
backend/.venv/Scripts/pip install -r backend/requirements.txt -r backend/requirements-dev.txt

# Frontend deps
cd frontend && npm install && cd ..
```

`backend/.env` and `frontend/.env.local` are gitignored and already point
at the local stack in a working checkout:

- `backend/.env` → `DATABASE_URL=postgresql://postgres:@127.0.0.1:55432/mact_local`
- `frontend/.env.local` → `NEXT_PUBLIC_API_URL=http://localhost:8000`

Never commit either file, and never repoint them at Neon while using the
sandbox.

## 3. Daily loop (offline)

```bash
# 1. Start the sandbox Postgres (idempotent; creates both databases)
backend/.venv/Scripts/python.exe scripts/local_db.py start

# 2. Apply schema migrations (reads backend/.env → sandbox)
backend/.venv/Scripts/python.exe scripts/apply_manual_migrations.py

# 3. Seed sample data (first time only; safe to re-run)
DATABASE_URL="postgresql://postgres:@127.0.0.1:55432/mact_local" \
    backend/.venv/Scripts/python.exe scripts/seed_local_sample_data.py

# 4. Run the backend (first boot after a cold start takes ~10s on Windows)
cd backend
.venv/Scripts/python.exe -m uvicorn app.main:app --port 8000

# 5. Run the frontend (separate terminal)
cd frontend && npm run dev        # http://localhost:3000
```

Sandbox logins (these exist **only** in the sandbox):

| Username | Password | Purpose |
|---|---|---|
| `localadmin` | `LocalAdmin#2026` | Super admin |
| `MCT-0001` | `MemberTest#2026` | Normal member login |
| `MCT-0003` | `MemberTest#2026` | Starts in the forced first-login password-reset flow (the stored password changes once you complete it) |

## 4. Test gates before pushing

**Gate 1 — pytest, all green:**

```bash
cd backend
DATABASE_URL="postgresql://postgres:@127.0.0.1:55432/mact_test" \
    .venv/Scripts/python.exe -m pytest -q
```

This is pointed at `mact_test`, **not** `mact_local`, on purpose: the suite
creates and truncates tables freely. Never point `DATABASE_URL` at a real
cooperative's database for this.

**Gate 2 — smoke test against the running local backend:**

```bash
backend/.venv/Scripts/python.exe scripts/smoke_test.py --base-url http://127.0.0.1:8000
```

Defaults already match the seeded sandbox (`localadmin` / `MCT-0001`). It
leaves behind one pending loan application (payment reference `SMOKE-...`)
in `mact_local` — that is sample data and stays local.

## 5. Stage 2 — verify on a throwaway Neon branch

Only needed when the change touches schema, migrations, or deploy wiring
(routine app-code changes can stop at Section 4). The goal: exercise the
migration runner and the real HTTP stack against Neon **before** touching
production.

1. **Create a throwaway branch** in the Neon console (branch off
   production, or a fresh branch — anything it receives is disposable).
   Copy its connection string.
2. **Apply schema to the branch** (the `--allow-remote` flag is a
   deliberate speed bump — the script only writes schema, never sample
   data):

   ```bash
   DATABASE_URL="postgresql://...ep-xxx-branch.../db?sslmode=require" \
       backend/.venv/Scripts/python.exe scripts/apply_manual_migrations.py --allow-remote
   ```

3. **Point a backend at the branch** — either a Vercel Preview deployment
   (push your branch / open a PR, override `DATABASE_URL` for the Preview
   environment), or locally:

   ```bash
   cd backend
   DATABASE_URL="postgresql://...ep-xxx-branch.../db?sslmode=require" \
       .venv/Scripts/python.exe -m uvicorn app.main:app --port 8000
   ```

4. **Smoke test the branch target.** Use accounts that exist in the branch
   (a branch off production inherited your real staff/member accounts;
   sample-data accounts do NOT exist there). The smoke test creates a real
   loan-application row, so remote targets require the explicit `--yes`
   acknowledgement — and must be throwaway environments only, **never
   production**:

   ```bash
   backend/.venv/Scripts/python.exe scripts/smoke_test.py \
       --base-url <preview-url-or-http://127.0.0.1:8000> \
       --admin-user <...> --admin-pass <...> \
       --member-user <PSN> --member-pass <...> --yes
   ```

5. **Tear the branch down** when the verification is done.

## 6. Push and deploy

- `git push` to `main` → Vercel redeploys whichever project(s) changed
  (see `DEPLOYMENT.md` Part G). Preview deployments are the disposable
  counterparts of Section 5.
- If you added a **new** `scripts/manual_migration_*.sql`, apply it to
  production the same way previous schema changes were applied (the
  files are idempotent; the branch dry-run in Section 5 is what catches
  ordering mistakes first). Never run `seed_local_sample_data.py`
  anywhere but the sandbox — it will refuse a non-sandbox URL anyway.

## 7. Housekeeping & troubleshooting

```bash
backend/.venv/Scripts/python.exe scripts/local_db.py status   # running?
backend/.venv/Scripts/python.exe scripts/local_db.py stop     # stop, data kept
backend/.venv/Scripts/python.exe scripts/local_db.py psql     # interactive shell
backend/.venv/Scripts/python.exe scripts/local_db.py reset --yes   # wipe .local/ and start fresh
```

| Symptom | Likely cause | Fix |
|---|---|---|
| `pytest` skips everything | `DATABASE_URL` not set | Export it per Gate 1 (venv python, `mact_test`) |
| `seed_local_sample_data.py` refuses to run | `DATABASE_URL` is not 127.0.0.1:55432 | Working as intended — point it at the sandbox |
| Seed says entities already exist | It is idempotent | Nothing to do |
| Backend takes ~10s on first request | Cold start on Windows | Wait for `/api/health` to respond |
| `pgserver` missing | Dev requirements not installed | `backend/.venv/Scripts/pip install -r backend/requirements-dev.txt` |
| Want a truly clean local slate | Sample data accumulated | `local_db.py reset --yes` then re-run Section 3 steps 1–3 |

`.local/` is the only place sandbox state lives — deleting it (or
`reset --yes`) is always safe and affects nothing outside your machine.
