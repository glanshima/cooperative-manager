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
| `scripts/smoke_test.py` | End-to-end check over real HTTP against a running backend (health → admin login → member lookup → loan types → member login → member self → submit application → read back). Passing `--conflict-admin-user`/`--conflict-admin-pass` adds the Next-of-Kin conflict check (login as a member-linked admin; the conflicted member stays **visible** in search/detail reads but each row carries `conflicted=true`, writes return `409 member_conflict`, and an unconflicted admin reads unflagged) for 10 steps total. **Step 7 creates a real loan-application row**, and step 10 an inert draft deduction, in the target database. | repo root |

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
| `smoke_nok_admin` | `SmokeNok#2026` | Super admin linked to fixture member `MCT-9001`, whose Next of Kin is `MCT-0001` — used only by the smoke test's `--conflict-admin-user` check |

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
and, with the conflict flags, one inert draft deduction for `MCT-0001`
(its confirm is blocked, so no money is recognised) — that is sample data
and stays local.

To include the Next-of-Kin conflict check (steps 9–10), pass the seeded
fixture admin; the primary admin must not be that linked account:

```bash
backend/.venv/Scripts/python.exe scripts/smoke_test.py --base-url http://127.0.0.1:8000 \
    --conflict-admin-user smoke_nok_admin --conflict-admin-pass 'SmokeNok#2026'
```

Without the flags the script runs the 8 core steps and prints that it
skipped the conflict check. With them it expects **10/10**.

Steps 9–10 assert the conflict-of-interest **read** policy: the linked
officer still gets every record back — searchable, listable, readable by
id — each flagged `conflicted=true`, while every write against that member
still returns `409 member_conflict` and an unlinked admin reads the same
rows unflagged. For deductions, the policy is narrower: a conflicted officer
may enter a draft at the expected amounts (the contribution on the member
record, the instalment fixed at disbursement) — that's clerical work. What
stays blocked is any discretionary amount (an 'other' line, or a line that
differs from the expectation) and any money-recognition step (confirm,
not_deducted, void).

**Gate 3 — frontend tests, types, and production build:**

```bash
cd frontend
npx vitest run --pool=forks    # the default thread pool can OOM on Windows
npx tsc --noEmit
npm run build
```

Use `--pool=forks` rather than plain `npm test`: the default worker-thread
pool intermittently dies with `FATAL ERROR: Zone Allocation failed -
process out of memory` on this machine. All three must exit clean — Vitest
prints the suite total, `tsc` and `next build` print nothing but errors.

**Gate 4 — eyeball the flows in the browser** (`http://localhost:3000`,
not `127.0.0.1:3000` — the backend's `ALLOWED_ORIGINS` only whitelists the
`localhost` origin, so requests from the IP origin fail CORS preflight with
403 and the pages silently show nothing). Minimum sweep for this branch's
work:

- Admin `localadmin`: `/members` — contribution amount in Add/Edit
  (Edit shows it locked with the change-request note), the "Contribution
  change requests" panel, "Record exit" on member rows; `/admin/deductions`
  — Enter tab worklist (due queue, expected totals, auto-filled form,
  draft + Undo), Ledger tab (Edit/Submit/Confirm/Not deducted/Void, print
  schedule); `/admin/settings` module toggles.
- Member `MCT-0001`: `/dashboard` — Monthly contribution card and "Request
  change" (button becomes "Request pending" after submitting).
- Conflicted reads: log in as `smoke_nok_admin` — `MCT-0001` stays listed
  with a "⚠ conflict" badge, no action buttons anywhere, and the pending
  request from that member shows the conflict notice instead of
  Approve/Reject.

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
   loan-application row (plus an inert draft deduction when the conflict
   flags are passed), so remote targets require the explicit `--yes`
   acknowledgement — and must be throwaway environments only, **never
   production**:

   ```bash
   backend/.venv/Scripts/python.exe scripts/smoke_test.py \
       --base-url <preview-url-or-http://127.0.0.1:8000> \
       --admin-user <...> --admin-pass <...> \
       --member-user <PSN> --member-pass <...> --yes
   ```

   To cover the Next-of-Kin conflict steps on the branch, it needs the
   same fixture shape as the sandbox: an **admin** account linked to a
   member whose Next of Kin is the smoke member (the relationship must be
   `active` with `conflict_of_interest = true`). If the branch's inherited
   data already has one, add `--conflict-admin-user`/`--conflict-admin-pass`
   and expect 10/10. Otherwise run the 8 core steps and rely on Gate 1 for
   the conflict rules — do not write a throwaway fixture to any database
   other than a disposable branch.

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
| `vitest` dies with `Zone Allocation failed - process out of memory` | Default worker-thread pool on Windows | Run Gate 3 with `npx vitest run --pool=forks` |
| Browser pages load but every API call fails / nothing renders | Opened via `127.0.0.1:3000`, which `ALLOWED_ORIGINS` doesn't whitelist | Use `http://localhost:3000` |
| Want a truly clean local slate | Sample data accumulated | `local_db.py reset --yes` then re-run Section 3 steps 1–3 |

`.local/` is the only place sandbox state lives — deleting it (or
`reset --yes`) is always safe and affects nothing outside your machine.
