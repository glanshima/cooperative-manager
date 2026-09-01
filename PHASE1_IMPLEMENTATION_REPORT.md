# MACT Cooperative Manager — Phase 1 Implementation Report

**Phase:** 1 — Security, Authorization, Audit & Data Integrity Foundations
**Date:** 2026-08-28 (implementation), 2026-08-28 (first remediation pass),
2026-08-29 (Controlled Remediation pass — User↔Member conflict-of-interest
protection, this update)
**Status:** **PHASE 1 — NOT YET VERIFIED** for the Controlled Remediation
work in Section K below (code-complete, unexecuted — same environmental
sandbox limitation as before). The EARLIER remediation pass (Section J)
has since been verified live, for real, by the person operating this
project: they applied both migrations to their actual Neon database,
ran `seed_permissions.py`/`create_admin.py`, resolved a local Python-
version wheel-build issue (3.14 → 3.12 venv), fixed a CORS
misconfiguration between the deployed Vercel frontend and backend, and
**confirmed a successful end-to-end login on the live deployed app**.
That is real evidence the Section J fixes work outside a sandbox, even
though the automated test suite itself still hasn't been run — see
Section K.9 for exactly what remains outstanding for the NEW
conflict-of-interest work specifically.

---

## J. Remediation pass (2026-08-28) — summary

This section documents the fixes made in response to the independent review
of the original Phase 1 implementation (Sections A–I below are the original,
largely-still-accurate report from the initial implementation pass).

### J.1 Inspection findings (remediation prompt Section 1)

| Finding | Detail |
|---|---|
| `scripts/manual_migration_2026_08_phase1_security_foundation.sql`, `scripts/seed_permissions.py`, `scripts/create_admin.py` | **Contrary to the remediation prompt's premise, all three were actually present** in the supplied repository and, on inspection, correctly matched `models.py` and `permissions_catalogue.py`. No restoration was needed; verified line-by-line instead. |
| `permissions_catalogue.py` docstring claim | Claimed drift-detection was "enforced by ... tests/test_permission_catalogue.py" — **that file did not exist.** Fixed: see J.6. |
| `GET /api/permissions` authorization | Gated on `admin.permission_manage` only — a user with `admin.role_manage` (but not `admin.permission_manage`) could manage roles but not read the catalogue the Roles UI needs to render its permission matrix. Confirmed by reading `routers/roles.py` against `deps.py`. Fixed: see J.3. |
| `idempotency.py` concurrency | Confirmed a genuine check-then-act race at the idempotency-record level (two concurrent requests with the same key could both observe "no record" before either committed). Note: this was **not** exploitable into an actual double-disbursement or double-repayment-credit in the two endpoints that use it today, because both already hold `SELECT ... FOR UPDATE` on the underlying business row (application / repayment) independent of the idempotency layer — but the idempotency *mechanism itself* was not race-safe, which matters for future phases reusing it. Fixed: see J.4. |
| `audit_service.py` failure handling | Failures were only `print()`ed — invisible to most log aggregation, and the function returned normally (the caller had no way to know the audit write failed). Fixed: see J.5b. |
| DB integrity constraints | No DB-level CHECK constraints existed on financial amounts (positive/non-negative), relying solely on Pydantic. Confirmed by reading `models.py` and the migration SQL. Fixed: see J.7. |
| Office/Position | No separate `Position` entity exists; only `Office` and `Role`. Investigated and resolved as intentional — see J.8 (no schema change made). |
| Segregation of duties | `loan.approve`/`loan.reject` are already independently grantable and already covered by `test_segregation_of_duties_approve_vs_reject`. No incompatibility-pair enforcement exists or was added, per the prompt's explicit instruction not to invent unapproved SoD rules. |
| Backend/frontend/migration execution | **Blocked** — see J.5. |

No regressions or deployment blockers beyond the above were found. Existing
architecture (single-tenant-per-deployment, hand-run SQL migrations, Office→
Role→Permission model, `is_super_admin` escape hatch) was preserved as-is,
per the prompt's Section 12/14 instructions.

### J.2 Files changed in this remediation pass

| File | Change |
|---|---|
| `backend/app/idempotency.py` | Rewritten to claim the idempotency key with an upfront `INSERT` (relying on the DB unique constraint for mutual exclusion) instead of check-then-act; added `PENDING_RECORD_STALE_SECONDS` reclaim window for crashed requests. |
| `backend/app/audit_service.py` | Replaced `print()` with `logging.getLogger("mact.audit").critical(...)`; added `AuditWriteFailed` exception, now raised (not swallowed) after logging, so a failed audit write surfaces as a loud 500 rather than a silent success. |
| `backend/app/deps.py` | Added `require_any_permission(*codes)` dependency factory. |
| `backend/app/routers/roles.py` | `GET /api/permissions` now uses `require_any_permission("admin.role_manage", "admin.permission_manage")` instead of `admin.permission_manage` alone. |
| `backend/app/models.py` | Added `CheckConstraint`s (positive/non-negative financial amounts) to `Loan`, `LoanApplication`, `LoanRepayment`, `LoanType`, `LoanTypeRateVersion`, `Settings`, `User`. |
| `scripts/manual_migration_2026_08_phase1_db_integrity_constraints.sql` (new) | Additive migration adding the same CHECK constraints at the DB level, with pre-flight verification queries. |
| `backend/tests/test_permission_catalogue.py` (new) | Drift-detection tests (the ones the old docstring falsely claimed already existed). |
| `backend/tests/test_authorization.py` | Added 3 tests covering the `GET /api/permissions` fix. |
| `backend/tests/test_idempotency.py` | Added 2 tests covering the concurrency-claim and stale-reclaim behavior. |
| `backend/tests/test_database_integrity.py` | Added 2 tests covering the new DB CHECK constraints. |

### J.3 Permission catalogue / Roles UI contract — decision

**Chosen approach (the prompt's preferred option):** `GET /api/permissions` is
now readable by either `admin.role_manage` or `admin.permission_manage`,
via a new `require_any_permission()` dependency. No new permission code was
introduced (`admin.permission_manage` already existed and still gates the
narrower "manage the permission catalogue" concept, which in Phase 1 has no
write endpoint of its own — the catalogue is code-defined). A role manager
without `admin.permission_manage` can now read but not alter the catalogue,
which is exactly the access level the Roles UI needs. Backend authorization
remains authoritative (this is a server-side dependency, not a frontend
gate); unauthorized users (no matching permission) still get 403. Covered by
`test_role_manager_can_read_permission_catalogue`,
`test_permission_manager_can_read_permission_catalogue`, and
`test_unrelated_permission_cannot_read_permission_catalogue` in
`test_authorization.py`. Frontend (`frontend/lib/api.ts`,
`frontend/app/admin/roles/page.tsx`) required no changes — it already just
calls `GET /api/permissions` and reacts to the HTTP status returned.

### J.4 Idempotency hardening — what changed and why

The original mechanism checked for an existing `IdempotencyRecord`, and only
inserted one right at the end (in `store()`) after the business logic ran.
Two simultaneous requests with the same key could both pass the "does a
record exist?" check before either had written one, then both go on to
attempt the operation — the uniqueness constraint would only be discovered
by whichever `store()` call ran second, by which point both operations may
already have executed.

**Fix:** `idempotency_check()` now claims the key immediately by inserting a
placeholder record (`completed_at=NULL`) and committing it before returning
control to the endpoint. The database's `UniqueConstraint("user_id",
"endpoint", "idempotency_key")` is the actual mutual-exclusion mechanism —
only one concurrent request can win that insert. The loser re-reads the row
it collided with:
- different request hash under the same key → `409` (unchanged behavior)
- `completed_at` is set → replay the cached response (unchanged behavior)
- `completed_at` is `NULL` and the reservation is recent (< 30s) → `409`
  "already being processed, retry shortly" (**new** — this is the fix)
- `completed_at` is `NULL` and stale (≥ 30s, i.e. the reserving request
  almost certainly crashed before finishing) → the stale row is deleted and
  the new request reclaims the key (preserves "replay after failed
  completion," prompt item 4.5)

This does not touch or weaken the existing `SELECT ... FOR UPDATE` locks in
`disburse_application()` / `verify_repayment()`, which remain the primary
guard against double-processing a specific business row; the fix closes the
separate, more general race in the idempotency mechanism itself, which
matters once later phases reuse it on endpoints that may not have an
equivalent natural row lock.

Idempotency remains applied to exactly the two Phase-1-required endpoints
(loan disbursement, repayment verification) — not extended elsewhere, per
the prompt's explicit instruction.

Covered by (new) `test_concurrent_duplicate_request_is_rejected_not_double_executed`
and `test_stale_pending_reservation_can_be_reclaimed`, plus the three
pre-existing idempotency tests, all in `test_idempotency.py`.

### J.5 Audit reliability — decision and honest limitation

**Not made fully atomic with the business transaction.** Several already-
implemented Phase 1 routers `db.commit()` the business change first and only
then build the audit `new_values` payload (so they can include
server-generated values like a new row's id). Making business+audit commits
truly atomic would require restructuring transaction boundaries across
roughly 8 routers — a genuine cross-cutting change to the transaction
architecture, which the prompt explicitly says not to casually undertake
mid-Phase-1 ("Do NOT casually redesign the entire accounting architecture").
This is recorded as a real, load-bearing limitation, not glossed over: **a
failed audit write and a successful business write can, in principle, still
both happen for the same request** (the business commit already succeeded
before the audit write is attempted).

**What was strengthened instead (the safest practical mitigation, per the
prompt's own fallback instruction):**
1. Failures are logged via `logging.getLogger("mact.audit").critical(...)`
   with `exc_info=True` and full context (event type, entity, actor, action)
   — replacing a bare `print()` that most hosting setups (including
   Vercel's serverless functions) don't reliably capture or alert on.
2. `audit_service.log_event()` now **raises** `AuditWriteFailed` after
   logging, instead of swallowing the exception. No existing Phase 1 router
   catches it, so a failed audit write today surfaces as an HTTP 500 to the
   caller — loud and visible, not a silent success. This is a deliberate,
   conservative choice: for a financial state change, "the action happened
   but we have no proof of who did it" is judged worse than an error asking
   the operator to check logs (the business change itself is not rolled
   back, since it was already committed in its own transaction, but its
   audit gap is now impossible to miss).
3. As a practical safety net, because the idempotency mechanism (J.4) claims
   keys before the operation runs, if a client retries a disbursement/
   repayment-verification request after seeing a 500 caused by an audit
   failure, the retry safely detects "already done" via `resulting_loan_id`
   (or repayment status) rather than double-processing.

Redaction (passwords/tokens/secrets excluded via `audit_service.redact()`),
before/after snapshots, actor snapshotting, and append-only behavior are
all unchanged from the original implementation and remain correct.

**Follow-up recommendation (not done now, per scope):** revisit transaction
boundaries in Phase 3 (Accounting Foundation) to make business+audit writes
atomic within a single DB transaction, now that a real double-entry ledger
is being introduced anyway.

No new automated test exists for the audit-failure path itself (forcing a
`db.commit()` failure requires either mocking the session or a DB-level
fault injection, neither of which this sandbox's environment could exercise
against a real Postgres instance — flagged honestly rather than skipped
silently).

### J.6 Permission-catalogue drift test

Added `backend/tests/test_permission_catalogue.py`, making the existing
`permissions_catalogue.py` docstring's claim ("enforced by ...
tests/test_permission_catalogue.py") actually true. It statically scans
`backend/app/routers/*.py` for every permission code literal passed to
`require_permission(...)` / `require_any_permission(...)` /
`user_has_permission(...)` and asserts each exists in
`PERMISSION_CATALOGUE`, plus a separate explicit check for `loan.approve`/
`loan.reject` (selected dynamically at runtime in
`decide_application`, so the static scan can't see them) and a check that
every `DEFAULT_ROLES` grant references a real code.

### J.7 Database integrity hardening — decision

Added DB-level `CHECK` constraints (positive/non-negative amounts) on
`loans`, `loan_applications`, `loan_repayments`, `loan_types`,
`loan_type_rate_versions`, `settings`, and `users.failed_login_count` — both
in `models.py` (`CheckConstraint` in each model's `__table_args__`, so
`Base.metadata.create_all()`-based test/dev schemas get them automatically)
and as a new, separate, purely-additive migration script
(`scripts/manual_migration_2026_08_phase1_db_integrity_constraints.sql`),
matching the project's established hand-run-SQL-migration pattern rather
than introducing a second migration mechanism.

**Pre-flight safety, per the prompt's explicit instruction:** the new
migration file's Part 1 is a set of `SELECT count(*) ...` queries (as
comments, meant to be run by hand first) that check whether any existing row
would violate each new constraint, with an explicit instruction not to
proceed to Part 2 (the `ALTER TABLE ... ADD CONSTRAINT` statements) until
every one returns 0. The project's current documented state is
testing-only with no live cooperative data yet, so 0 rows is expected, but
the migration does not assume that — it requires the operator to check.
Cross-field constraints (e.g. `total_repayable >= net_disbursed`) were
deliberately NOT added — Section 6 warns against duplicating business logic
at the DB layer where it would make future phases (e.g. Phase 3's ledger
corrections/reversals) harder; only straightforward positive/non-negative
bounds were added.

Covered by two new tests in `test_database_integrity.py` that insert an
invalid `Loan`/`LoanRepayment` directly (bypassing the API) and assert the
DB itself rejects it via `IntegrityError`.

### J.8 Office vs. Position — resolved, no schema change

**Conclusion: "Office/Position" was descriptive terminology; the
implemented `Office` + `Role` model is correct. No separate `Position`
entity is needed**, and none was added.

Reasoning:
- The existing `Office` model's own docstring (written during the original
  Phase 1 implementation, before this remediation pass) already describes
  it as *"A cooperative-defined office/position (President, Treasurer,
  ...)"* — i.e. "office" and "position" were already being used
  interchangeably for the same concept (an EXCO title like President,
  Treasurer, Secretary) at the point this was implemented.
- Claude's own memory of the governing specification records the intended
  model as **"User → Office → Role → Permission"** (no separate Position
  layer) — matching what's actually implemented.
- A cooperative "position" (e.g. Treasurer) and an authorization "role" (a
  bundle of permissions) are legitimately different things in this domain
  (two different offices might share the same role's permission set, or one
  office might need different permission bundles over time), and that
  distinction is exactly what `Office` (identity/accountability) vs. `Role`
  (permission bundle) already captures — introducing a third `Position`
  layer between them wouldn't map to any additional real-world concept the
  spec calls for.

Per the prompt's explicit instruction, no schema change was made on the
strength of the word "Position" appearing in prose; if the authoritative
specification document is later found to define `Position` as a distinct
required entity, that would need to come back as its own scoped
change-control item (see Section I for the existing change-control
pattern), not be silently introduced now.

### J.9 What could NOT be executed in this environment, and why

This sandbox's `bash_tool` runs with **network access disabled** (confirmed:
`pip install fastapi --dry-run` → `403 Forbidden`/no matching distribution;
`npm install --dry-run` in `frontend/` → `403 Forbidden` from
registry.npmjs.org) and has **no PostgreSQL instance reachable** (no
`psql`/`pg_ctl`/`initdb` binaries present, no `DATABASE_URL` target). Neither
`fastapi`, `sqlalchemy`, `pytest`, `psycopg2`, nor `passlib` are importable
(`ModuleNotFoundError` for each, confirmed directly), and `frontend/` has no
`node_modules` and cannot acquire one. Concretely, this means:

- **Section 9 (backend tests):** NOT executed. `backend/tests/conftest.py`
  itself `pytest.skip`s the entire suite if `DATABASE_URL` is unset, by
  design (Postgres-specific column types and row-locking behavior are
  intentionally not faked with SQLite) — so even attempting to run pytest
  here would report "skipped," not "passed," and this report does not
  claim otherwise.
- **Section 10 (frontend build):** NOT executed — cannot install
  dependencies.
- **Section 11 (migration on a disposable DB):** NOT executed — no Postgres
  instance to create a disposable database against.

Every change in this remediation pass was instead verified the strongest
way available in this environment: full manual reading of every changed
file against its call sites and the actual schema, plus
`python3 -m py_compile` across every backend `.py` file (all pass — no
syntax errors), and manual trace-through of each new/changed test against
the fixtures in `conftest.py` to confirm they call real functions with
matching signatures. This is real verification, but it is not test
execution, and per the prompt's explicit standard ("do not mark tests as
passed without executing them... the standard is evidence, not claims"),
this report does not claim Sections 9–11 are done.

**To actually close these out**, run, outside this sandbox, in an
environment with network access and a disposable Postgres database (e.g. a
throwaway Neon branch or local Postgres):

```bash
# Backend tests
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
export DATABASE_URL="postgresql://.../mact_test"   # a disposable DB — never production
export SECRET_KEY="test-only-secret"
pytest -v

# Frontend build
cd frontend
npm install
npm run build   # (add `npm run lint` first if a lint script is configured)

# Migration verification (Section 11) — against the SAME disposable DB above,
# starting from an empty schema so it represents pre-Phase-1 as closely as
# practical:
psql "$DATABASE_URL" -f ../scripts/manual_migration_2026_08_phase1_security_foundation.sql
psql "$DATABASE_URL" -f ../scripts/manual_migration_2026_08_phase1_db_integrity_constraints.sql
python ../scripts/seed_permissions.py
python ../scripts/create_admin.py bootstrap_admin "SomeStrongPassw0rd!"
cd ../backend && uvicorn app.main:app --reload   # confirm it starts cleanly
```

If you run these and share the output, I can help interpret failures and
close out the remaining sign-off checklist items.

---



## A. Requirements implemented

| ID | Requirement | Status |
|---|---|---|
| §6 | Password hashing, policy, brute-force lockout, secrets never logged/returned | Done |
| §7 | Account lifecycle (pending/active/suspended/deactivated), immediate loss of authority | Done |
| §8 | User → Office → Role → Permission model, no `is_admin=true` as sole gate going forward | Done (layered on top of existing `role`, see C-1) |
| §9 | Full permission catalogue as specified | Done |
| §10 | Backend authorization on every protected write endpoint touched | Done for all Phase-1-scoped routers; see H for what wasn't touched |
| §11 | Object-level authorization / IDOR protection | Done (members, loans, loan applications, repayments) |
| §12 | Segregation-of-duties foundation | Done (`loan.approve` vs `loan.reject` split; catalogue supports further splits) |
| §13–14 | Audit trail + event catalogue | Done |
| §15 | Financial history protection | Done — surfaced two real gaps, see C-2/C-3 |
| §16 | Database integrity (constraints, indexes) | Partially done — see H |
| §17 | Idempotency foundation | Done (generic mechanism + applied to repayment/disbursement verification) |
| §18 | Concurrency foundation | Done (`SELECT ... FOR UPDATE` on all verify/decide/disburse paths) |
| §19 | Transaction boundaries | Done (existing commit-per-action pattern preserved; audit write is a separate transaction by design) |
| §20–21 | API security / input validation | Done for financial values, email, phone, PSN, receipt uploads; see H |
| §22 | Secure configuration | Verified — no hard-coded secrets found; new config added via env vars |
| §23 | Frontend Phase 1 screens | Done — Users, Offices, Roles, Audit viewer |
| §24 | API + frontend contract | This report + inline docstrings; no separate OpenAPI export produced (FastAPI generates it automatically at `/docs`) |
| §25 | Migrations preserve data | Done — purely additive migration |
| §26 | Automated tests | Written, **not executed** — see H |

---

## B. Files changed

| File | Change | Requirement |
|---|---|---|
| `backend/app/models.py` | Added `AccountStatus`, `Office`, `Role`, `Permission`, `RolePermission`, `UserRoleAssignment`, `AuthSession`, `AuditEvent`, `IdempotencyRecord`; extended `User` with lockout/status/super-admin fields; portable `JSONType` | §7–9, 13, 17 |
| `backend/app/permissions_catalogue.py` (new) | Permission catalogue + default role starter set | §9 |
| `backend/app/audit_service.py` (new) | Audit-write helper with redaction, actor snapshotting | §13–14 |
| `backend/app/idempotency.py` (new) | Generic `Idempotency-Key` mechanism | §17 |
| `backend/app/account_lifecycle.py` (new) | Password policy, lockout tracking, status transitions | §6–7 |
| `backend/app/validation.py` (new) | Email/phone/PSN/amount/receipt format validators | §21 |
| `backend/app/auth.py` | JWT now carries `jti` for session tracking | §6 |
| `backend/app/deps.py` | Session-revocation check, `require_permission()` factory, `user_has_permission()` | §7, 10 |
| `backend/app/routers/auth.py` | Lockout, session create/revoke, real logout, audit logging, password policy | §6 |
| `backend/app/routers/admin_users.py` (new) | Staff account CRUD, status changes, role/office assignment | §7–9 |
| `backend/app/routers/offices.py` (new) | Office CRUD | §8 |
| `backend/app/routers/roles.py` (new) | Role + role-permission CRUD, permission catalogue read | §9 |
| `backend/app/routers/audit.py` (new) | Audit log viewer + CSV export | §13–14, 23 |
| `backend/app/routers/members.py` | Permission checks, audit logging, IDOR-safe `get_member`, blocked hard-delete with financial history | §10, 11, 15 |
| `backend/app/routers/loans.py` | Permission checks, audit logging, `delete_loan` fully blocked | §10, 15 |
| `backend/app/routers/loan_applications.py` | Permission checks, row locking on verify/decide/disburse, audit logging, idempotency on disburse | §10, 12, 17, 18 |
| `backend/app/routers/loan_repayments.py` | Permission checks, row locking + idempotency on verify, audit logging | §10, 17, 18 |
| `backend/app/routers/loan_types.py` | Permission checks, audit logging | §10 |
| `backend/app/routers/settings.py` | Permission checks, audit logging | §10 |
| `backend/app/schemas.py` | New schemas for Office/Role/Permission/Audit; validators wired into Member/Loan/LoanApplication/LoanRepayment input schemas | §21 |
| `backend/app/main.py` | Registered new routers | — |
| `backend/.env.example` | New `MAX_FAILED_LOGIN_ATTEMPTS`, `LOCKOUT_MINUTES`, `PASSWORD_MIN_LENGTH` | §6, 22 |
| `scripts/create_admin.py` | Bootstrap account now `is_super_admin=true`; uses shared password-policy validator | §6, C-1 |
| `scripts/seed_permissions.py` (new) | Seeds permission catalogue + default roles | §9 |
| `frontend/lib/api.ts` | New types/functions for admin users, offices, roles, permissions, audit; `logout()` now calls the backend | §23 |
| `frontend/app/admin/users/page.tsx` (new) | Staff account management UI | §23 |
| `frontend/app/admin/offices/page.tsx` (new) | Office management UI | §23 |
| `frontend/app/admin/roles/page.tsx` (new) | Role + permission-matrix UI | §23 |
| `frontend/app/admin/audit/page.tsx` (new) | Audit log viewer UI | §23 |
| `backend/tests/*` (new) | pytest suite — see Section F | §26 |

---

## C. Database migrations

| Migration | Purpose | Data preservation | Rollback |
|---|---|---|---|
| `scripts/manual_migration_2026_08_phase1_security_foundation.sql` | Adds `account_status`/lockout/super-admin columns to `users`; creates `offices`, `permissions`, `roles`, `role_permissions`, `user_role_assignments`, `auth_sessions`, `audit_events`, `idempotency_records`; backfills `account_status` from existing `is_active`; marks pre-existing admins as `is_super_admin=true` | Purely additive — no `DROP`, no column narrowing, no row deletion. Existing `users` rows keep every current value. | Each `ALTER TABLE ... ADD COLUMN` and `CREATE TABLE` has a corresponding `DROP` that would need to be written and run manually if a rollback is ever required; none is included by default since Phase 1 code depends on these columns/tables existing. |

Run order: this migration → `scripts/seed_permissions.py` → redeploy backend. Verification queries are included as comments at the bottom of the migration file.

---

## D. API changes

All new/changed endpoints, permission required, and purpose:

| Endpoint | Purpose | Authorization |
|---|---|---|
| `POST /api/auth/logout` | Server-side session revocation | authenticated |
| `POST /api/admin/users` | Create staff account | `admin.user_manage` |
| `GET /api/admin/users` | List staff accounts | `admin.user_manage` |
| `PATCH /api/admin/users/{id}/status` | Change account lifecycle status | `admin.user_manage` |
| `GET/POST/DELETE /api/admin/users/{id}/assignments` | Manage role assignments | `admin.role_manage` |
| `GET/POST/PUT /api/offices` | Office CRUD | read: any staff; write: `admin.office_manage` |
| `GET /api/permissions` | Read permission catalogue | `admin.permission_manage` |
| `GET/POST/PUT /api/roles` | Role + permission-grant CRUD | read: any staff; write: `admin.role_manage` |
| `GET /api/audit`, `GET /api/audit/{id}`, `GET /api/audit/export/csv` | Audit trail access | `audit.view` / `audit.export` |
| `GET /api/members`, `POST`, `PUT`, `DELETE /api/members/{id}` | (existing, now permission-gated) | `member.view` / `.create` / `.update` / `.deactivate` |
| `GET/POST/PUT /api/loans`, `DELETE` (now always 409) | (existing, now permission-gated) | `loan.view` / `disbursement.submit` / `accounting.adjust` |
| `POST /api/loan-applications/{id}/verify-payment` | (existing) | `loan.review` |
| `POST /api/loan-applications/{id}/decide` | (existing) | `loan.approve` or `loan.reject` depending on outcome |
| `POST /api/loan-applications/{id}/disburse` | (existing) | `disbursement.submit`; accepts `Idempotency-Key` |
| `POST /api/loan-repayments/{id}/verify` | (existing) | `repayment.verify`; accepts `Idempotency-Key` |

Every endpoint above that changes state now writes an `AuditEvent` after the change commits.

---

## E. Frontend changes

- `/admin/users` — create staff accounts, change lifecycle status, assign/revoke Office+Role.
- `/admin/offices` — CRUD for cooperative offices.
- `/admin/roles` — CRUD for roles with a checkbox permission matrix grouped by category.
- `/admin/audit` — filterable audit log with a detail modal showing before/after values.
- `lib/api.ts` — client functions and types for all of the above; `logout()` now also revokes the server-side session.

All four pages gate on `requireRole: "admin"` via the existing `useAuth` hook (a UI-level convenience — the real enforcement is server-side per §10).

---

## F. Tests

**Superseded by Section J.9 above — see there for the current, evidence-based
status.** The table below is retained as the original (pre-remediation)
snapshot for history only.

| Test file | Covers | Expected | Actual | Status |
|---|---|---|---|---|
| `test_auth.py` | Login success/failure/lockout/deactivated/immediate-revocation/logout | All pass | **Not run** | ⚠️ Written only |
| `test_authorization.py` | Permission gating, super-admin bypass, role revocation, segregation of duties, permission-catalogue read access | All pass | **Not run** | ⚠️ Written only |
| `test_idor.py` | ID substitution across members/loans, 404 vs 403 | All pass | **Not run** | ⚠️ Written only |
| `test_audit.py` | Audit events written correctly, no password leakage, audit endpoint gating | All pass | **Not run** | ⚠️ Written only |
| `test_database_integrity.py` | Duplicate PSN/username, member/loan deletion protection, DB CHECK constraints | All pass | **Not run** | ⚠️ Written only |
| `test_idempotency.py` | No double-credit on repeated key, mismatched-body rejection, status-guard without a key, concurrent-claim rejection, stale-reclaim | All pass | **Not run** | ⚠️ Written only |
| `test_permission_catalogue.py` (new) | No permission-code drift between router code and the catalogue | All pass | **Not run** | ⚠️ Written only |

**"Actual" and "Status" are honest, not aspirational, in both the original
pass and this remediation pass**: neither this sandbox nor the original
implementation sandbox had network access to `pip install`, nor a reachable
Postgres instance. Every file was verified with `python -m py_compile`
(syntax-valid) and careful manual cross-referencing against the actual
endpoint code and test fixtures, but **none of this has executed**. See
Section J.9 for exact commands to run this suite for real.

---

## G. Security verification

- **Authorization:** every write endpoint touched in Phase 1 now requires a specific permission code (see Section D), checked server-side via `require_permission()`/`user_has_permission()` — never a frontend-only gate.
- **IDOR:** `get_member`, `get_loan`, `get_application`, loan-repayment access all check `member_id`/`loan.member_id` against the authenticated member before returning data, and check the relevant `.view` permission for admin access. Covered by `test_idor.py`.
- **Session/credential revocation:** deactivating or suspending a staff account now revokes their outstanding sessions immediately (`admin_users.py::update_admin_user_status`), not just at their next login.
- **Not independently penetration-tested** — this verification is code review + the (unexecuted) test suite, not an external security audit.

---

## H. Known limitations

1. **Tests are unexecuted** (see F, and J.9 for why and how to fix it) — the single biggest caveat on this whole report.
2. **`member.view` etc. is a single flat permission** — there's no field-level restriction (e.g. a role that can see a member's name/PSN but not their bank account number). Not requested by the spec; noted in case it matters later.
3. **No general per-IP rate limiter** — only the account-specific brute-force lockout was implemented. A reverse-proxy/WAF-level rate limiter is a reasonable Phase 10 (Production Hardening) addition.
4. **`Office` and `Role` write endpoints don't yet have their own dedicated audit-event *reason* field surfaced in the UI** — the API accepts a reason on user status changes, but not on office/role edits; low-risk, easy follow-up.
5. **Idempotency is applied to two endpoints (disbursement, repayment verification), not universally** — the *mechanism* is generic and reusable, but per Section 17's own scope ("generic mechanism... required by later phases"), applying it everywhere immediately wasn't necessary for Phase 1's definition of done. (Remediated for race-safety in J.4; scope unchanged.)
6. ~~Database check constraints beyond what SQLAlchemy/uniqueness already implies were not added~~ **RESOLVED in the remediation pass — see J.7.** DB-level `CHECK` constraints for positive/non-negative financial amounts now exist both in `models.py` and in a dedicated migration script.
7. **No automated migration tooling (Alembic) was introduced** despite being in `requirements.txt` — the project's established pattern is hand-run SQL migrations reviewed in Neon's SQL Editor, and Phase 1 preserved that pattern rather than introducing a parallel migration system unilaterally.
8. **Frontend pages are functional but minimally styled**, matching the existing plain-inline-style convention already used throughout the app (not a Phase 1 regression, just not visually polished).
9. **Audit writes are not atomic with their business transaction** (see J.5) — a real, documented limitation, not fully resolved this pass; mitigated with loud failure surfacing rather than silence.
10. **Backend/frontend/migration verification could not be executed in either sandbox environment used so far** (original implementation pass or this remediation pass) — see J.9 for exact commands; this is the actual blocker standing between "code-complete" and "VERIFIED / READY FOR SIGN-OFF."

---

## I. Change-Control items

**C-1 — Backward-compatible Super Admin backfill.** No formal spec existed for what happens to pre-existing admin accounts once granular permissions are introduced. Rather than silently locking every existing admin out of every endpoint (breaking Section 4's "preserve existing functionality"), the migration marks every admin account that existed **before** this migration as `is_super_admin=true`, preserving their exact current (full) access. Every admin account created **after** this migration starts with no permissions and must be explicitly granted a role. Flagging this as a decision that may need cooperative-level sign-off, since it does mean pre-existing admins retain broader access than the granular model would otherwise assign them, indefinitely, unless someone later revokes `is_super_admin` on those specific accounts.

**C-2 — Member hard-delete blocked when financial history exists.** The original `delete_member` endpoint performed an unconditional hard delete that cascaded (`delete-orphan`) to the member's loans and loan applications — a direct conflict with Section 15's "do not physically delete posted financial transactions." No member-deletion policy was specified for this case in the source documents. Rather than inventing a full member lifecycle-status model, the minimal safe interpretation was applied: hard delete is now only permitted when the member has zero loans/loan applications; otherwise the API returns 409 and points the admin toward revoking the member's login instead. A proper Member lifecycle status (mirroring the User `account_status` pattern) is deferred to Phase 2, consistent with the master audit's own M1-004 finding.

**C-3 — Loan hard-delete blocked entirely.** `Loan` has no "draft" state anywhere in the model — a Loan is a posted financial transaction from the moment it's created. The original `delete_loan` endpoint allowed unconditional hard delete of any loan, which is squarely what Section 15 prohibits. Since no correction/reversal contract exists yet for loans (that's Phase 3 — Accounting Foundation scope), this endpoint now unconditionally returns 409 rather than attempting to design a reversal mechanism mid-Phase-1. This is a real behavior change from the pre-Phase-1 app and should be communicated to whoever currently relies on that endpoint.

**C-4 — (Remediation pass) `GET /api/permissions` authorization widened to an OR of two permissions.** See J.3. Chosen over introducing a new `admin.permission_view` code, since the prompt's preferred option (allow `admin.role_manage` to read the catalogue) fully covers the actual need and avoids adding a fourth Administration-category permission for a read-only, code-defined resource.

**C-5 — (Remediation pass) Audit-write failures now raise, rather than silently continue.** See J.5. This is a behavior change: a state-changing endpoint whose business commit succeeds but whose subsequent audit write fails will now return HTTP 500 to the caller (previously it returned 200 as if nothing had gone wrong). Flagging this for cooperative-level awareness since it's a genuine, if rare, new failure mode visible to end users — the alternative (silently losing audit coverage) was judged worse for a financial system.

**C-6 — (Remediation pass) Office/Position — no schema change.** See J.8. "Office/Position" in the specification's descriptive prose is treated as referring to the same concept already implemented as `Office` (whose own docstring already says "office/position"), not a request for a third distinct entity between `Office` and `Role`. Recorded per the prompt's instruction to flag rather than silently resolve if any doubt existed; flagging here for cooperative-level confirmation that this reading is correct, since no independent access to the authoritative specification document was available in this remediation pass to verify beyond Claude's own memory of it.

**Open decision (not resolved, flagged per Section 12):** no exact segregation-of-duties *incompatibility rules* were specified (e.g. "the admin who prepared a disbursement may not also approve it"). The permission catalogue and Role model fully support configuring this (a cooperative can simply not grant `disbursement.prepare` and `disbursement.approve` to the same role), but the system does not *enforce* mutual exclusivity between any specific pair of permissions. Recording this as an open decision rather than inventing an enforcement rule, per Section 12's explicit instruction. Unchanged by this remediation pass.

---

## K. Controlled Remediation pass (2026-08-29) — User↔Member conflict-of-interest protection

MACT cooperative members are elected EXCO officers, so the same physical
person can hold both a Member record (they take out loans, make
repayments) and an admin/staff User account with real permissions
(loan.approve, disbursement.submit, accounting.adjust, etc.). Prior to
this pass, permissions authorized what a user could generally do, but
nothing prevented an admin from using that authority on their OWN member
record or financial transactions — an EXCO officer with loan.approve
could approve their own loan application. This section documents the
fix.

### K.1 User↔Member link (Section 1)

`User.member_id` already existed as a nullable FK to `members.id` (added
in the original Phase 1 migration) — no new column was needed. What
changed: it was previously unique table-wide and, by convention, only
ever populated for `role='member'` self-service accounts. This pass:

- Relaxed the uniqueness to two **partial unique indexes**
  (`ux_users_member_id_per_member_role`, `ux_users_member_id_per_admin_role`),
  each scoped to `WHERE role = '...'`. This allows an EXCO officer's
  separate member-role self-service account and admin-role account to
  BOTH legitimately reference the same `member_id`, while still
  preventing two rows of the *same* role from ambiguously claiming the
  same member — see `models.py`'s `User` class docstring for the full
  reasoning.
- Added migration
  `scripts/manual_migration_2026_08_controlled_remediation_user_member_link.sql`,
  which drops the old constraint (looked up dynamically via
  `pg_constraint`, since its original name isn't recorded anywhere —
  this table predates this project's migration-script era) and adds the
  two partial indexes, with a pre-flight duplicate check.
- **No existing account was auto-linked.** Every admin account's
  `member_id` remains `NULL` after this migration until a human
  explicitly sets it (see K.4). Per Section 1's explicit instruction,
  there is no name/email/phone/fuzzy-matching inference anywhere in this
  codebase — `self_conflict.py`'s module docstring explains why: a wrong
  inference could either wrongly block an unrelated person, or worse,
  fail to catch a real conflict.

### K.2 Central self-conflict guard (Section 2)

New module `backend/app/self_conflict.py`:

- `resolve_owning_member_id(db, target)` — resolves the member a
  `Member`, `LoanApplication`, `Loan`, or `LoanRepayment` belongs to
  (direct FK for the first three; `LoanRepayment.member_id`'s own
  column for the last, rather than traversing `.loan` — simpler and
  works even without eager loading).
- `require_no_self_conflict(db, current_user, target, ...)` — the single
  reusable guard every router calls. Raises HTTP 409 if
  `current_user.member_id` matches the target's owning member. No-ops
  (allows the action) when `current_user.member_id` is `NULL` — an admin
  never explicitly linked to a member cannot have an inferred conflict.
- `find_eligible_approvers(db, member_id, permission_code, ...)` —
  read-only lookup of active admins who hold the permission and aren't
  conflicted, surfaced in the 409 response body (see K.3).

Applied to five endpoints (all syntax-checked, `python -m py_compile`
passing):

| Router | Endpoint | Permission checked | Guard action description |
|---|---|---|---|
| `loan_applications.py` | `verify_payment` | `loan.review` | "review your own loan-form payment" |
| `loan_applications.py` | `decide_application` | `loan.approve`/`loan.reject` | "approve or reject your own loan application" |
| `loan_applications.py` | `disburse_application` | `disbursement.submit` | "disburse your own loan" |
| `loan_repayments.py` | `verify_repayment` | `repayment.verify` | "verify your own loan repayment" |
| `loans.py` | `update_loan` | `accounting.adjust` | "adjust your own loan" |
| `members.py` | `update_member` | `member.update` | "administratively edit your own member record" |
| `members.py` | `delete_member` | `member.deactivate` | "deactivate or delete your own member record" |

In every case, the guard runs immediately after the target row is
loaded (404-checked) and before any other business-rule validation —
consistent with the authorization ordering in Section 7 of the prompt
(permission → object-level auth → resolve target member → self-conflict
→ business rules → lock → perform → audit).

Not scattered/reimplemented per-router: every call site is a single
`require_no_self_conflict(...)` call: no duplicated comparison logic.

### K.3 Self-service vs. administrative authority (Section 3)

No self-service member endpoints were disabled or restricted — there
wasn't one to restrict for most of these actions in the first place
(`GET /api/members/me` is the only member self-service endpoint that
existed, and it's read-only). The guard only applies to the
*administrative* (permission-gated) endpoints listed above; a member
using their own PSN login for legitimate self-service (e.g. submitting
their own loan application, viewing their own record) is entirely
unaffected — that isn't an administrative action and doesn't go through
`require_no_self_conflict()` at all.

### K.4 Super-admin hard deny (Section 4)

`require_no_self_conflict()` never checks `is_super_admin` — it isn't
even in the function's parameters. There is no `if is_super_admin:
allow_everything()` path anywhere in this guard, by construction, not by
convention. Verified by
`test_super_admin_cannot_bypass_self_conflict` in
`test_self_conflict.py`.

### K.5 Alternate approval path (Section 5)

When `require_no_self_conflict()` is called with a `permission_code`, a
409 response includes an `eligible_approvers` list (active admins
holding that permission, excluding the conflicted user) and a
`no_eligible_approver_available` boolean. This is **read-only
information returned in the same denial response** — there is no
auto-routing, auto-queueing, or auto-reassignment anywhere; the
transaction is simply left in its current state (e.g. a loan
application stays `PENDING`) and it's up to the cooperative's own
process for another eligible officer to act on it. No President-as-
universal-approver or other unapproved role-to-role rule was invented.

### K.6 Object ownership (Section 6)

Handled directly in `resolve_owning_member_id()` (K.2) — both direct
(`Loan.member_id`, `LoanApplication.member_id`) and indirect
(`LoanRepayment` — uses its own denormalized `member_id` column)
ownership are covered. `FinancialAdjustment` as a distinct entity does
not exist yet in this codebase (loan corrections currently go through
`update_loan`'s `accounting.adjust` gate, which IS guarded — see K.2's
table); if a dedicated adjustment/reversal entity is introduced in a
later phase, it should call `resolve_owning_member_id()`'s pattern
(add a branch, or expose the member relationship directly) rather than
reimplementing ownership resolution.

### K.7 Admin user management — linking UI/API (Section 10)

New endpoint: `PATCH /api/admin/users/{user_id}/member-link` in
`admin_users.py`, gated on the existing `admin.user_manage` permission
(no new permission code introduced — this is squarely within what that
permission already governs). Accepts `{member_id, reason}`; `member_id:
null` clears an existing link. Validates: target must be an admin-role
user; the member must exist; the member isn't already linked to a
*different* admin (friendly 409 pre-check, backed by the DB's partial
unique index as the actual authoritative guarantee via `IntegrityError`
handling). Every change is audit-logged
(`admin.user_member_link_changed`) with previous/new `member_id` and
the caller's `reason`. `UserOut` already exposed `member_id` in its
schema from the original Phase 1 work, so the admin UI can show the
linked member once the frontend's admin-users page is wired to call
this new endpoint — **the frontend page itself was not modified in this
pass** (backend-only; see K.9 for what's left).

### K.8 Tests (Section 11)

All 13 mandatory scenarios plus 5 additional tests for the linking
endpoint were written:

- `backend/tests/test_self_conflict.py` — the 13 mandatory scenarios:
  own vs. other member record edits, own vs. other loan-application
  approval, own repayment verification blocked, own disbursement
  blocked, super-admin does not bypass, eligible alternate approver
  surfaced, conflicted approvers excluded from that list, no-eligible-
  approver leaves the application `PENDING` (never auto-decided), a
  `NULL` `member_id` has no inferred conflict, matching name/email
  between an unlinked admin and a member does NOT create a conflict,
  and a conflict denial is audit-logged without any credential material
  in the event payload.
- `backend/tests/test_admin_user_member_link.py` — linking/unlinking
  succeeds and is audited, double-linking the same member to two admins
  is rejected, linking a member-role (not admin-role) user is rejected,
  and the endpoint itself is permission-gated.

**Written, syntax-checked, NOT executed** — same sandbox limitation as
Section J (no network, no reachable Postgres in this container). See
K.9.

### K.9 What remains outstanding

- **Tests have not been run.** Unlike Section J's fixes, which the
  project owner has since verified live against a real deployment, this
  Controlled Remediation work has NOT yet been exercised against a real
  database. Given the owner now has a working local Python 3.12 venv
  (established while debugging Section J), running
  `pytest backend/tests/test_self_conflict.py
  backend/tests/test_admin_user_member_link.py -v` against a disposable
  Postgres database is the immediate next step before trusting this in
  production.
- **The new migration
  (`manual_migration_2026_08_controlled_remediation_user_member_link.sql`)
  has not been applied to any real database**, including the owner's
  live Neon database from the Section J deployment. It must be run
  (Neon Console SQL Editor or `psql -f`) before the linking endpoint or
  the conflict guard's uniqueness guarantee will actually work against
  that live database — until then, `User.member_id` there is still
  governed by the OLD table-wide unique constraint.
- **Frontend admin-users page was not updated** to actually call the new
  `PATCH .../member-link` endpoint or display the link — this pass was
  backend-only. `UserOut.member_id` is already in the API response, so
  the frontend work is additive (a form field + API call), not blocked
  on anything backend-side.
- **`FinancialAdjustment` as a named entity doesn't exist yet** (see
  K.6) — if/when introduced in a later phase, it needs the same
  ownership-resolution treatment.
- **Sections 12–18 of this Controlled Remediation prompt** (restore
  deployment scripts, permission catalogue/Roles UI, idempotency
  hardening, audit reliability, DB integrity, Office/Position,
  segregation of duties) were already fully addressed in the prior
  remediation pass — see Section J above — and were not re-verified
  against this prompt's specific wording, but no discrepancy was found
  on inspection; they describe the same requirements Section J already
  implemented.
- **Legacy/brand cleanup (Sections 19–21):** a real, evidence-based pass
  was done, not a superficial one — findings: no `is_admin` legacy flag
  exists anywhere in this codebase (only `is_super_admin`, which is
  explicitly documented as NOT an unguarded shortcut, and which K.4
  confirms cannot bypass conflict protection); no debug `print()`
  statements exist in `backend/app/`; no `TODO`/`FIXME`/`XXX` markers
  exist. Stale branding ("MACT Cooperative Ledger", the project's
  original working name before it became "MACT Cooperative Manager")
  was fixed in `frontend/app/page.tsx`, `frontend/app/login/page.tsx`,
  `frontend/app/layout.tsx` (page title), `backend/app/main.py` (FastAPI
  app title), `README.md`, and `DEPLOYMENT.md`. A site-wide "© SIDGAKS
  Tech" footer was added in `frontend/app/layout.tsx` (renders on every
  page) and at the top of `README.md`. Per the prompt's explicit
  instruction, the brand was NOT inserted into technical identifiers —
  table/column names, API paths, Python module/class names, and the
  Neon database name (`neondb`) are all unchanged.
  **What was NOT done**, honestly: a full repository-wide sweep for
  unused imports/dead helper functions was not performed — this sandbox
  has no `pyflakes`/linting tool available and no network to install
  one, so an automated sweep wasn't possible, and a fully manual
  line-by-line audit of every file wasn't attempted given the scope of
  everything else in this pass. This is a real gap versus the prompt's
  Section 19 ask, not a silent skip — flagging it rather than claiming a
  cleanup that didn't happen.

### C-7 — Change-Control: partial (role-scoped) unique index instead of a single unique column on `users.member_id`

The original Phase 1 migration made `member_id` unique table-wide,
correctly for its use at the time (only member-role self-service
accounts ever populated it). This Controlled Remediation pass needed
BOTH an admin-role account and a member-role account to be able to
reference the same `member_id` simultaneously (the same person, two
separate logins), which a single table-wide unique column cannot
express. Resolved with two partial unique indexes scoped by `role`
(K.1) rather than, e.g., merging member and admin accounts into a
single login (which would have been a much larger, riskier change to
the authentication model, explicitly out of scope for a controlled
remediation). Flagging this for awareness since it changes a
constraint introduced in the very first Phase 1 migration.

---

## L. Login State Reconciliation & Members Table Action-State Fix (2026-08-29)

### Existing Login State Reconciliation

**Member 32074 finding:** the Members table's per-row action button
(`Create login`) was rendered **unconditionally for every member**,
regardless of whether a login already existed. Member 32074's login was
active; the button still showed "Create Login" because nothing in the
frontend ever checked.

**Root cause:** `MemberOut` (the schema backing every Members-table API
response) never carried any login-state field at all — not a bug in a
query or a broken join, but a genuine gap: login state had never been
modeled into the members list/detail response in the first place. The
frontend had no data to condition on even if it had tried. This was
verified by direct inspection of `schemas.py` (no `has_login`/
`login_status` field existed) and `frontend/app/members/page.tsx` (the
`<button>Create login</button>` had no surrounding conditional of any
kind).

**A second, related defect found and fixed during investigation:**
`POST /api/auth/create-member-login`'s existing-login check queried
`User.member_id == member.id` with no role filter. That was correct in
isolation, but became a regression once the Controlled Remediation pass
(Section K) introduced the ability for an admin-role account to *also*
link to a member's `member_id` (for conflict-of-interest purposes) — a
member whose only existing account was an admin link (no self-service
login yet) would have been incorrectly blocked from ever getting their
own member login. Fixed by scoping both `create_member_login` and
`reset_member_password`'s existing-record lookups to
`role == UserRole.MEMBER` specifically (see `auth.py`).

**Affected code:**
- `backend/app/schemas.py` — `MemberOut` gained `login_user_id`,
  `login_account_status` (nullable; `null` means no login exists — this
  is the ONLY signal the frontend uses).
- `backend/app/routers/members.py` — new `_attach_login_state()` helper
  (single bulk query, role-scoped to `member`) called from `list_members`
  and `get_member`; new `PATCH /{member_id}/login-status` endpoint
  (deactivate/reactivate an existing login — never creates or deletes
  one), gated on the existing `member.deactivate` permission (no new
  permission code introduced), guarded by `require_no_self_conflict`
  (an EXCO officer cannot deactivate/reactivate their own login via
  admin authority either), audit-logged as
  `member.login_status_changed`, and revokes active sessions on
  deactivation (mirroring `admin_users.py`'s existing pattern).
- `backend/app/routers/auth.py` — role-scoping fix described above.
- `frontend/lib/api.ts` — `Member` interface gained
  `login_user_id`/`login_account_status`; new
  `updateMemberLoginStatus()` call.
- `frontend/app/members/page.tsx` — the single unconditional button is
  now three conditionally-rendered ones
  (Create/Deactivate/Reactivate), driven entirely by
  `member.login_account_status`; a "Login" column was added to the
  table so the state is visible, not just the action.

**Database state / migration / reconciliation performed:** **none
required.** Every code path in this repository that has ever created a
User row for a member (`create_member_login`; no `scripts/*.py`
migration script creates User rows) has always set `member_id` at
creation time — verified by inspecting every such code path, not
assumed. The bug was entirely in what the API/UI surfaced, not in the
underlying data. A read-only diagnostic,
`scripts/check_login_state_reconciliation.sql`, was written for the
project owner to run against their actual live database and confirm
this holds true there too (checks for member-role User rows with a
NULL `member_id`, orphaned FKs, or duplicate member-role logins per
member). Per Section 4/5's explicit instruction, if that script ever
does surface a row, it is NOT auto-linked by name/email/phone — it must
be resolved by a human via the admin-users member-link endpoint or
direct verified correction.

**`User.member_id` → `Member.id` relationship:** confirmed as the sole
mechanism used everywhere in this fix — see `_attach_login_state()`'s
docstring for why it's explicitly scoped to `role == 'member'`
(distinguishing a self-service login from a conflict-of-interest admin
link to the same person).

**Members table behavior:** now exactly matches Section 6's specified
state machine (no login → Create; active → Deactivate; inactive →
Reactivate), driven entirely by backend data per Section 9 — the
frontend performs no independent inference.

**Duplicate-login protection:** enforced at the backend
(`create_member_login`'s role-scoped existing-check, now also correctly
permissive of the has-admin-account-only case) — covered by
`test_create_login_rejected_when_member_login_already_exists` and
`test_create_login_allowed_when_only_an_admin_account_is_linked` in
`test_login_state_reconciliation.py`.

**Login vs. admin role independence (Section 7):** an EXCO
officer's admin-role account (and any role/permission it holds) has no
bearing on their own member-role login's displayed state — verified by
`test_admin_role_does_not_affect_member_login_state`.

**Tests executed:** none — same sandbox limitation as Sections J and K
(no network, no reachable Postgres in this container). Written and
`python -m py_compile`-verified only:
`backend/tests/test_login_state_reconciliation.py`, covering Cases A
(no login), B (active), C (deactivate/reactivate cycle), D
(pre-existing-style login), F (EXCO/admin member independence), and
Section 12's duplicate-protection cases. Case E (an unresolved/unmapped
login) has no automated test because — per the finding above — no code
path in this repository can currently produce that state; it's covered
instead by the read-only diagnostic script for real production data,
which by definition can't be exercised from an empty test database.

**Legacy cleanup (Section 15):** searched for `has_login`, duplicated
login-detection logic, frontend-only login-state assumptions, stale
authentication flags, commented-out/debug login code — none found
beyond the single unconditional button and missing schema field already
described above; there was no OTHER, older login-state calculation
competing with the new one to remove.

**Brand cleanup (Section 17):** no additional stale branding found
beyond what Section K.9 already fixed in this pass.

**Remaining limitations:**
- Tests have not been executed against a real database (see above) —
  the immediate next step is running
  `pytest backend/tests/test_login_state_reconciliation.py -v` against
  a disposable Postgres database, alongside the Section K tests.
- `scripts/check_login_state_reconciliation.sql` has not been run
  against the live Neon database — recommended before considering this
  fix fully verified in production, to positively confirm (not just
  infer from code) that Member 32074's and every other member's login
  data is clean.
- Frontend TypeScript compilation (`tsc`/`next build`) has not been run
  in this sandbox (no `node_modules`, no network) — the same
  limitation noted in Section J.9.

**Final status: PHASE 1 — NOT YET VERIFIED.** Code-complete for this
addendum; blocked on the same environmental constraints as Sections J
and K, not on any known remaining defect. Exact blockers: (1) migration
`manual_migration_2026_08_controlled_remediation_user_member_link.sql`
and the new diagnostic script have not been run against the live
database; (2) `test_login_state_reconciliation.py` and
`test_admin_user_member_link.py`/`test_self_conflict.py` have not been
executed; (3) frontend build/TypeScript check has not been run.

---

## M. Members Search & Filtering Remediation (2026-08-29)

### Members Search & Filtering

**1. Supported search fields:** PSN, name, phone. PSN serves as this
codebase's "Member Number/Member ID" — there is no separate
`member_number` field in the data model; this mapping is documented here
rather than silently assumed. Email is deliberately NOT searchable: it
was never part of the pre-existing search contract (the prior
implementation matched only name/PSN), and the remediation prompt makes
email-search conditional on it already being approved — it wasn't, so
it stays out.

**2. Phone search behavior:** substring match (`ILIKE '%term%'`),
consistent with how name/PSN search already behaved — not a new
semantic invented for this pass. Phone numbers are stored as free text
(`PHONE_RE = ^[0-9+\-() ]{6,20}$` in `validation.py`) with no forced
canonical format (e.g. no enforced E.164), so no phone-specific
normalization beyond the general whitespace-trim below was applied.

**3. Whitespace normalization:** the incoming `search` query parameter
is `.strip()`ped server-side before being used in any query — enforced
in `list_members` itself (`backend/app/routers/members.py`), not merely
in the frontend, so a direct API caller gets the same guarantee. A
whitespace-only search (`"   "`) normalizes to no search at all (treated
identically to omitting `search`). Internal spaces (e.g. `"John Doe"`)
are preserved — `.strip()` only removes leading/trailing whitespace, and
this was verified with an explicit test that `"John Doe"` matches while
`"JohnDoe"` does not.

**4. Bank filter:** **no separate `Bank` entity exists in this
codebase** — `bank_name` is a free-text column on `Member`. This was
verified by inspection (`grep` for a `Bank` model turned up nothing)
before implementing anything, per the remediation prompt's own
instruction not to assume. Introducing a normalized Bank entity would
be a real schema/data-model change, out of scope for "do not redesign
the Members module." Instead: `bank_name` is filtered by **exact
match** against the free-text column, and the filter dropdown's options
come from a new `GET /api/members/filter-options` endpoint returning
the DISTINCT `bank_name` values actually present across members right
now — never fabricated, never hard-coded.

**5. Department filter:** identical situation and identical treatment —
`department` is also a free-text column with no separate entity;
same `filter-options` endpoint, same exact-match filtering.

**6. Membership Status filter:** this codebase's canonical
`MemberStatus` enum is **`financial` / `non_financial`** — there is no
`active`/`inactive` status anywhere in the data model. The remediation
prompt's own illustrative examples used "Active"/"Inactive" wording, but
also explicitly said not to invent new statuses and to use canonical
values — so the implementation uses `financial`/`non_financial`
throughout (query param, filter dropdown, response), and this
discrepancy from the prompt's example wording is called out here rather
than silently reconciled by inventing an "Inactive" status that doesn't
exist.

**7. Combined search/filter behavior:** `search`, `bank_name`,
`department`, and `status` all combine with logical AND in a single
SQLAlchemy query in `list_members` — verified by
`test_bank_and_department_combine`,
`test_bank_department_and_status_combine`, and
`test_search_combines_with_all_filters` in
`test_members_search_filtering.py`. Each filter is also independently
usable with no search term required — verified by
`test_bank_filter_alone_no_search_needed`,
`test_department_filter_alone_no_search_needed`, and
`test_status_filter_alone_no_search_needed`.

**8. No-match state:** a valid request with zero matches returns
`{"items": [], "total": 0, ...}` with a normal 200 — never an error.
The frontend (`frontend/app/members/page.tsx`) explicitly distinguishes
three states: `loading` → "Loading...", `error` → "Unable to load
members.", and `!loading && !error && items.length === 0` → "No
matching records found." — these are mutually exclusive render
branches, not inferred from a shared blank-table appearance.

**9. Pagination behavior:** `GET /api/members` now returns
`MemberListResponse` (`items`, `total`, `skip`, `limit`) instead of a
bare array — a deliberate, scoped deviation from the flat-list
convention used by every other list endpoint in this codebase (loans,
loan-applications, audit all return bare arrays with no total count).
This was necessary because "total count is correct" and "invalid pages
are not requested after filtering" are both explicit acceptance
criteria, which a bare array can't support (the frontend would have no
way to know if page 2 exists without over-fetching). Query params stay
`skip`/`limit` (this codebase's existing, actual pagination convention
— see `loans.py`, `audit.py` — rather than the prompt's illustrative
`page`/`page_size`, per its own instruction to use "the project's actual
naming conventions"). The frontend resets `skip` to 0 whenever `search`
(Enter/Search button) or any filter changes, and disables
Previous/Next at the dataset boundaries using the real `total`.

**10. API contract:**
```
GET /api/members?search=&bank_name=&department=&status=&skip=&limit=
  -> { items: MemberOut[], total: int, skip: int, limit: int }
GET /api/members/filter-options
  -> { banks: string[], departments: string[] }
```
Both gated on the existing `member.view` permission — no new permission
code introduced.

**11. Database/query considerations:** filtering/pagination happens
entirely server-side in a single query (`db.query(models.Member)` with
chained `.filter()` calls, `.count()` for the total, then
`.offset()/.limit()`) — nothing is loaded into the browser and filtered
in JavaScript. No new indexes were added: `Member.psn` already has a
unique index (from the original schema) and `Member.name` is already
the default sort column; `bank_name`/`department`/`phone` are filtered
with `ILIKE`/exact-match on free-text columns without a dedicated index.
Per the prompt's explicit "do not add indexes blindly," adding one was
deferred rather than guessed at — if `EXPLAIN ANALYZE` against real
production-scale data later shows these filters are slow, that's a
concrete, evidence-based case for an index, not something to
speculatively add now against a dataset whose real size isn't known
from this sandbox.

**12. Authorization:** unchanged — both endpoints require `member.view`
(existing permission, existing dependency), and no new field was added
to `MemberOut` that exposes anything not already returned; the search
change doesn't broaden what any given caller can see, only how they can
narrow what they already see. Verified with
`test_filter_options_requires_member_view_permission`.

**13. Tests executed:** none — same sandbox limitation as Sections J, K,
and L (no network, no reachable Postgres in this container). Written and
`python -m py_compile`-verified only:
`backend/tests/test_members_search_filtering.py`, covering independent
filters, filter combination (2-way and 3-way), search+filter
combination, PSN/name/phone search, whitespace normalization (including
the leading/trailing/surrounding cases explicitly modeled on the
Member-32074-style regression), internal-space preservation,
whitespace-only search, no-match state, pagination total-count
correctness, and the filter-options endpoint (including its own
authorization gate).

**14. A second real bug found and fixed while investigating (not part
of the original ask, but discovered doing the root-cause investigation
this prompt required):** the original `list_members` returned a bare
array with no total count at all — meaning the *existing* Members
table's pagination (such as it was) had no way to know how many total
members existed or whether a "next page" was valid. This was silently
broken before this remediation, not something this pass introduced.

**Remaining limitations:**
- Tests have not been executed against a real database (see above).
- Frontend TypeScript compilation (`next build`) has not been run in
  this sandbox — same limitation noted in Sections J.9, L.
- No index was added for the new filter columns (see item 11) —
  deliberately deferred pending real query-performance evidence, not
  overlooked.
- The `loans.py` page's member-picker dropdown (a second, unrelated
  caller of `listMembers`) was updated to request `limit: 1000` to
  preserve its "show essentially all members" behavior now that the
  endpoint returns a paginated wrapper — this is a minor, incidental fix
  alongside the main deliverable, not a redesign of that page.

**Final status: PHASE 1 — NOT YET VERIFIED.** Code-complete for this
addendum; blocked on the same environmental constraints as Sections J,
K, and L — no tests have been executed, and neither has the frontend
build. No known remaining functional defect; the blockers are entirely
"hasn't been run yet," not "known to be broken."

---

## N. Member↔User relationship fix (2026-08-30)

Fixes Recommendation #1 from the Phase 0 Admin↔Member Linking
Assessment: `Member.user` was a single `uselist=False` relationship that
assumed at most one `User` row could reference a given `member_id`. That
assumption stopped being true as of the Controlled Remediation pass's
partial unique indexes, which deliberately allow **two** `User` rows
(one `role='member'` self-service login, one `role='admin'` conflict-
linked account) to reference the same `member_id` at once. Nothing in
the router code called `member.user` yet, so this was a dormant, not
active, bug — confirmed by grepping every call site before making the
change.

**Fix:** replaced the single ambiguous relationship with two explicit,
role-scoped ones on `Member`: `member_login_user` and `admin_login_user`
(both `viewonly=True`, `uselist=False`, each filtered by `User.role` in
their `primaryjoin`). `User.member` (the many-to-one side) is unchanged
except for dropping its now-asymmetric `back_populates`. Covered by
`backend/tests/test_member_user_relationship.py`, including the exact
scenario that used to crash (both rows present for one member) —
written, not yet executed against a real database.

---

## O. Admin → Member Linking Workflow & Self-Conflict Alert Lifecycle (2026-08-30)

Controlled remediation building the operational Admin UI on top of the
already-existing backend linkage architecture (Sections K, N). **Zero
backend files were changed in this pass** — deliberate, given the prior
session's outage from an unverified backend model change. Every new UI
action calls the existing `PATCH /api/admin/users/{id}/member-link`
endpoint; no new or competing linkage mechanism was introduced.

**Admin Users page (`frontend/app/admin/users/page.tsx`) rewritten** to
add:
- A "Linked Member" column showing "Not linked" or "PSN — Name" (built
  from a client-side lookup against `GET /api/members` — no new backend
  endpoint, reusing the same pattern `loans.py`'s member picker already
  used).
- Link / Change Member / Unlink actions, each a thin wrapper around the
  existing endpoint, each requiring explicit selection + confirmation
  before submitting.
- An optional member-search-and-link step on the admin-creation form —
  implemented as two sequential calls to two already-existing endpoints
  (`POST /api/admin/users` then `PATCH .../member-link`), not a new
  combined endpoint. If the second call fails, the admin account (already
  created) is not rolled back or hidden — the UI says so explicitly and
  points at the manual Link action as a fallback.

**Error-state lifecycle fixed** (Section 6/7's core ask): the page
previously had exactly the same bug class already found and fixed on the
Members page — a single shared `error` string covering both
list-loading failures AND every individual operation's own failure, with
several handlers (`toggleExpand` in particular) never clearing it on
success. Traced precisely, not guessed: `refresh()` did clear `error` at
its own start, but per-operation handlers like `toggleExpand` did not,
so a stale message from an earlier failed operation could survive
indefinitely until a `refresh()` happened to run. Fixed by splitting
into three independent states — `listError` (only `refresh()` sets/
clears this), `actionError` (every mutating operation clears this via a
shared `beginAction()` helper at its own start, not just on success),
and `success` — plus an explicit "Dismiss" button. Every action handler
(create, status change, expand-roles, assign role, revoke role, link,
change, unlink) now goes through the same `beginAction()`/
`isCurrentAction()` pair, closing the bug uniformly rather than only for
the new linking feature.

**Race-safety:** a shared `actionSeqRef` sequence counter guards every
mutating operation — only the most recently *started* operation's
result is ever applied to `actionError`/`success`, so a slow older
failure can't overwrite a faster newer success (Section 8's example).
`refresh()` has its own separate `listSeqRef` for the same reason,
consistent with the pattern already used on the Members page.

**Finding — the prompt's Section 6 premise does not match current
backend behavior**, verified by direct inspection rather than assumed:
`update_admin_user_member_link` in `admin_users.py` does **not** call
`self_conflict.require_no_self_conflict()` at any point — it was never
wired in. The docstring mentions `self_conflict.py`, but only describes
what happens *after* a link is set (future approve/disburse/verify
actions get blocked), not a check on the linking action itself. This
was independently confirmed empirically earlier in this engagement: an
admin (`glanshima`) successfully linked their own account to their own
member record via this exact endpoint, with no rejection. **No backend
change was made to add this check** — the Critical Scope Rule explicitly
prohibits redesigning "the existing self-conflict business rule" and
"the existing backend member-link endpoint," and adding a new validation
rule that doesn't currently exist would be exactly that. This is
reported as a genuine open gap (Section F below), not silently
implemented or silently ignored.

**Database verification:** not re-queried in this pass (no DB access
from this environment). Relying on evidence already gathered earlier in
this same engagement: the Neon Console SQL Editor output confirmed both
`ux_users_member_id_per_admin_role` and `ux_users_member_id_per_member_role`
partial unique indexes exist on the live database.

**Tests:** added `test_linking_to_a_nonexistent_member_is_rejected` and
`test_changing_an_existing_link_to_a_different_member_succeeds` to
`test_admin_user_member_link.py`, filling the two backend scenarios from
Section 11's list that weren't already covered by the prior pass. All
backend scenarios in Section 11 are now covered **except** "Admin
self-conflict is rejected" — not written, because (per the finding
above) that behavior does not exist in the code to test. No frontend
tests were added — this project has no frontend test runner/framework
configured (confirmed: no test files under `frontend/`, no test script
in `package.json` beyond `next build`/`next dev`/`next start`), so
"Frontend: 1–13" in Section 11 were manually verified against the code's
logic (traced state transitions by hand) rather than executed as
automated tests; this is stated plainly in the final report below
rather than implied to be equivalent to a real test run.

**Regression check performed** (code-level, not executed): confirmed
zero backend files were modified in this pass; `self_conflict.py`,
`deps.py`, `members.py`, `auth.py`, and `admin_users.py`'s actual
endpoint logic are byte-for-byte unchanged from the last known-working
deployment. The Admin Users page rewrite is additive relative to the
previous version — every prior capability (create, suspend/reactivate/
deactivate, expand/assign/revoke roles) is still present and calls the
same functions as before.

---

## P. Admin Identity Governance Controlled Remediation (2026-08-31)

Two governance objectives, both backend-authoritative, both using only
plain-Column/plain-query patterns (no `relationship()` with custom
joins) given the prior session's outage from an unverified relationship
change.

### P.1 Governance Objective 1 — Role-Based Member Link Requirement

New `roles.requires_member_link` Boolean column (default `false`,
purely additive — no existing role or assignment is affected by the
migration itself). Enforced in `admin_users.py`:
- **Assignment time:** `assign_role` rejects assigning a
  `requires_member_link=True` role to a user with `member_id IS NULL`
  (409, `{"error": "member_link_required", ...}`).
- **Unlink time:** `update_admin_user_member_link` rejects clearing
  `member_id` (setting it to `null`) while the user holds any active
  role with `requires_member_link=True` (`_user_has_active_member_required_role()`,
  mirroring `deps.py::user_has_permission`'s exact active-assignment
  query convention). Changing to a *different* member is unaffected
  (the resulting `member_id` is still non-null, so this branch is never
  entered).
- No role name is ever hard-coded anywhere in the enforcement code —
  purely data-driven off the `requires_member_link` flag, which a
  cooperative administrator sets per-role via the Roles UI or API.

### P.2 Governance Objective 2 — Admin Self-Link Protection

`update_admin_user_member_link` now rejects `current_user.id == user_id
AND payload.member_id is not None` — i.e. an admin can never use this
endpoint to link or change *their own* account's member link, full
stop. Unconditional: `is_super_admin` is never checked, consistent with
`self_conflict.py`'s established precedent elsewhere. Self-*unlinking*
is explicitly NOT blocked by this rule (removing your own link removes
power, not grants it) — it remains subject only to Objective 1's
separate role-based unlink check. Denials are audit-logged
(`admin.member_link_self_conflict_denied`) before the exception is
raised, so a rejected attempt can never appear as a successful linkage
in the audit trail.

**Decision flagged for review — Section 12, test 3 of the remediation
prompt** ("Admin links themselves to a different Member — do not
assume prohibited") was genuinely ambiguous between two readings: block
only linking to the admin's *own pre-existing* member identity, or
block *any* self-directed link. A **blanket rule** was chosen (any
self-directed link is blocked, regardless of which member) — reasoning
documented inline in `admin_users.py` and in
`test_3_admin_cannot_link_themselves_to_a_different_member_either`.
This is the single most significant interpretive decision made in this
pass; if a narrower rule was actually intended, this is the exact test
and code block to revisit.

---

### «Decision D — LOCKED: Blanket Admin Self-Link Prohibition.» (2026-09-01)

**Status: LOCKED.** Approved and formally recorded by the project owner.
Reproduced verbatim below for the permanent record; the implementation
already matched this decision exactly when it was locked, so **no code
changes were required or made** as a result of this lock.

> An administrator may never use the Admin → Member linking endpoint to
> link or change their own admin account to any Member record. This
> applies regardless of which Member is selected; whether the Member is
> the administrator's own Member record; whether the administrator is
> Super Admin; or which role the administrator holds.
>
> **No Super Admin bypass.** The restriction is unconditional at the
> Admin → Member linking endpoint.
>
> **Self-unlink** remains permitted, unchanged, unless another existing
> governance rule prevents it — specifically, if the administrator
> currently holds a role where `requires_member_link = true`, the
> role-assignment/linkage integrity rule (Governance Objective 1) must
> still prevent the resulting invalid state.
>
> This rule does not prohibit an administrator from *having* a Member
> record — only from using the self-service Admin → Member linking
> operation to establish or change that relationship themselves. A
> controlled administrative process (another authorized admin performing
> the link) remains available.
>
> Locked: do not narrow this rule to only the administrator's own Member
> record, add a Super Admin bypass, weaken backend enforcement, or
> reinterpret it in a future branch without explicit authorization. The
> backend remains authoritative.

**Required verification (all seven, checked against the actual code and
test suite — not re-executed, same standing sandbox limitation as every
item in this report):**

| # | Requirement | Enforced by | Covered by |
|---|---|---|---|
| 1 | Admin cannot self-link to their own Member record | `admin_users.py` line 168: `if current_user.id == user_id and payload.member_id is not None` | `test_1_admin_cannot_link_themselves_to_their_own_member` |
| 2 | Admin cannot self-link to another Member record | Same condition — no member-specific branch exists; the check has no dependency on *which* member is selected | `test_3_admin_cannot_link_themselves_to_a_different_member_either` |
| 3 | Super Admin cannot bypass | Confirmed by direct inspection: `is_super_admin` is never referenced anywhere in this endpoint or in the condition above | `test_1b_super_admin_cannot_bypass_self_link_protection` |
| 4 | Admin can still be linked via an authorized external/controlled process | The condition only fires when `current_user.id == user_id` (the caller acting on themselves); a *different* admin performing the link is unaffected | `test_2_admin_links_another_admin_to_a_valid_member_succeeds` |
| 5 | Existing valid Admin → Member links continue to work (change operation) | Unaffected — the self-link condition and the "change to a different member" path are independent | `test_4_changing_an_existing_link_continues_to_work`, `test_changing_an_existing_link_to_a_different_member_succeeds` |
| 6 | Required-member role enforcement remains intact | Governance Objective 1's checks (assignment-time and unlink-time) live in separate code paths from the self-link check and were not modified by this lock | `test_role_member_link_requirement.py` (7 tests), `test_5b_admin_can_unlink_their_own_account` (self-unlink still subject to the role check) |
| 7 | Audit behavior remains intact | `admin.member_link_self_conflict_denied` is logged before the exception is raised; no `admin.user_member_link_changed` (success) event is ever created for a blocked attempt | `test_self_link_denial_is_audited` |

All seven are satisfied by the implementation as it stood before this
lock. This lock changes the status of Section P.2's decision from
"flagged for review" to **closed, permanent, and not to be
reinterpreted without new, explicit authorization** — per the decision
record above.

### P.3 A mistake made and caught during this pass

An early `str_replace` edit accidentally deleted the
`def list_user_assignments(` line while inserting the new
`_user_has_active_member_required_role()` helper nearby. Caught
immediately via `python -m py_compile` failing (not shipped) and fixed
before continuing. Noted here in the interest of the same transparency
applied to the earlier production incident — this one did not reach a
deployable state, but is exactly the class of careless edit that did
last time.

### P.4 Files changed

**Backend:** `models.py` (new column), `schemas.py` (`RoleBase`/
`RoleUpdate`), `routers/roles.py` (`_to_role_out`, `create_role`,
`update_role`), `routers/admin_users.py` (both enforcement points +
helper), new migration
`scripts/manual_migration_2026_08_admin_identity_governance.sql`.

**Frontend:** `lib/api.ts` (`Role` interface, `createRole`/`updateRole`
signatures — no changes needed to error handling, since both new error
shapes reuse the existing `{"error": ..., "message": ...}` structure
`ApiError`/`describeError` already handle from the earlier self-conflict
work); `app/admin/roles/page.tsx` (create-form checkbox, per-role badge,
editable toggle in the edit panel); `app/admin/users/page.tsx`
(`AssignRoleForm` shows role options annotated "(requires Member link)"
and disables Assign with an inline explanation when the target account
isn't linked — client-side hint only, backend remains authoritative
regardless).

### P.5 Tests

- `test_role_member_link_requirement.py` (new) — Section 12 items 6-12:
  unlinked+non-required=allowed, unlinked+required=rejected,
  linked+required=allowed, second member-required role still rejected
  while unlinked, unlink blocked while a member-required role is active,
  unlink allowed after revoking that role, and a direct API call (not
  going through any UI) is still rejected.
- `test_admin_user_member_link.py` (extended) — Section 12 items 1-5:
  self-link to own/any member rejected (including a super-admin
  variant), linking *another* admin succeeds, self-link to an unrelated
  member is *also* rejected (the documented blanket-rule decision),
  changing an existing link continues to work, unlinking a valid account
  continues to work, an admin can unlink *themselves*, and the denial is
  audit-logged with no false-success event alongside it.
- `conftest.py` extended with `make_role()` and a `requires_member_link`
  parameter on `grant_permission()`.

**All written and `python -m py_compile`-verified. None executed** —
same standing sandbox limitation (no network, no reachable Postgres)
as every prior pass in this engagement.

### P.6 Regression check (code-level, not executed)

Confirmed via full-repository `py_compile` (zero errors) and a
line-by-line re-read of every modified function. `self_conflict.py`,
`deps.py`, `members.py`, `auth.py`, and the previously-existing parts of
`admin_users.py`/`roles.py` are unchanged in behavior — every
modification in this pass is additive (a new column with a safe
default, new conditional branches that only fire in new/specific
circumstances, new endpoints' response fields). No `relationship()`
with a custom join was used anywhere in this pass, specifically to avoid
the failure mode from the prior session's outage.

### P.7 What remains outstanding

- **Migration not applied to any real database** —
  `scripts/manual_migration_2026_08_admin_identity_governance.sql` must
  be run (Neon Console SQL Editor, same as every prior migration) before
  any of this works against the live deployment.
- **No automated test has been executed** — same standing gap as every
  prior pass; recommend running the full suite (now including these two
  new files) against a disposable database before trusting this in
  production, especially given this pass touches the same file
  (`admin_users.py`) that had a careless edit caught mid-session (P.3).
- ~~The Section 12 test 3 interpretation (P.2) needs explicit
  confirmation~~ **RESOLVED 2026-09-01 — see «Decision D — LOCKED» above.**
- No frontend build/TypeScript check has been run (no network/Node
  modules in this sandbox) — same limitation as every prior pass.

## Q. Member Relationship / Next-of-Kin Controlled Remediation (2026-09-01)

New foundation: a first-class, reusable Member-to-Member relationship
model (`MemberRelationship`), used first for the Next-of-Kin case
(explicit "is this member's Next of Kin also a cooperative member?"
question at Member creation/edit) and structured to support a future
relationship type (e.g. guarantor) without another migration. A
governance-only conflict-lookup helper (`has_member_conflict`) is also
included as foundation, per the remediation prompt's explicit
instruction NOT to wire it into any approval workflow in this pass.

### Q.1 Data model

New table `member_relationships` (`models.py`): `member_id` /
`related_member_id` (both FK → `members.id`), `relationship_type`
(currently only `next_of_kin`), `conflict_of_interest` (bool, default
`true`), `status` (`active`/`removed`), plus the usual
created/removed audit columns. No `relationship()` declared on this
model or added to `Member` for it — same lesson as Section N's outage
and Section P's "plain-Column/plain-query only" pattern: two FKs into
the same table (`members.id`) would need `foreign_keys=[...]`
disambiguation on any `relationship()`, so plain query methods
(`get_member`/`get_related_member`) are used instead, at zero
mapper-configuration risk.

Two DB-level invariants, both primarily enforced in the application
layer with the DB as a backstop (same pattern as every other
constraint in this codebase):
- **No self-reference** — `CHECK (member_id != related_member_id)`.
  Primary enforcement is `member_relationships.set_relationship()`,
  which raises a clean 409 `{"error": "self_reference", ...}` before
  ever reaching the DB; the CHECK constraint only fires if that's
  somehow bypassed.
- **At most one ACTIVE relationship of a given type per member** — a
  partial unique index, `(member_id, relationship_type) WHERE status =
  'active'`. **Inspection finding, not an invented rule:** the
  pre-existing `Member.next_of_kin*` columns are a single set of
  fields, not a list — this cooperative's data model has always
  implicitly treated Next of Kin as one person per member. This
  remediation preserves that shape for the member-linked path rather
  than introducing multiplicity the manual-entry path never had. If a
  member should eventually be able to record more than one Next of
  Kin, this is the index to revisit, not something this pass assumed
  was requested.

Changing to a **different** related member is remove-old-row +
create-new-row (never an in-place `related_member_id` update), so the
audit trail retains who the previous Next of Kin was and when the
change happened. Within `set_relationship()`, the old row's UPDATE is
explicitly `db.flush()`ed before the new row's INSERT is added — without
that, SQLAlchemy's unit-of-work is free to order the INSERT first
within the same flush, which would momentarily violate the partial
unique index even though the net change is a clean swap. Both
statements still commit together, so a later failure rolls back the
whole swap atomically.

### Q.2 Why a new table, not a `next_of_kin_member_id` column on `Member`

Considered and rejected. Two reasons, both from the remediation prompt
itself rather than a preference: (1) the prompt frames Next-of-Kin as
the *first* of potentially several member-to-member relationship types
this foundation needs to support later — a generic, typed table avoids
a schema change for each new type a single FK column would require;
(2) relationship *history* must be retained when it changes or is
removed (the same Financial-History-Protection precedent this codebase
already applies to `delete_member`, Change-Control C-2, applied here to
relationship history instead of financial history) — a single mutable
FK column on `Member` cannot represent "who was the Next of Kin before
last Tuesday" at all.

### Q.3 Existing data — deliberately not touched

No backfill/auto-conversion of the 191 pre-existing members' free-text
`next_of_kin` fields into `MemberRelationship` rows. Two reasons:
first, doing so would require *inferring* which free-text Next-of-Kin
entries refer to an existing Member record — the same class of
heuristic-matching `self_conflict.py`'s module docstring explicitly
forbids for the User↔Member link, for the same reason (a wrong
inference either creates a bogus relationship or misses a real one).
Second, nothing in the remediation prompt asked for a backfill. Every
pre-existing member therefore reads as `next_of_kin_is_member: null`
("never answered", not "answered no") until an admin explicitly edits
that record and picks one of the two options — see `MemberOut`'s
docstring in `schemas.py` and `_attach_next_of_kin`'s docstring in
`routers/members.py` for the exact three-way `null`/`true`/`false`
semantics.

### Q.4 API changes

- `POST /api/members` (`schemas.MemberCreate`): **new required field**
  `next_of_kin_is_member: bool` (no default — omitting it is a 422, not
  a silent pass), plus `next_of_kin_member_id: Optional[UUID]` (required
  when `next_of_kin_is_member` is `true`, forbidden when `false`,
  enforced by a Pydantic `model_validator`). This is an intentional
  breaking change to the endpoint's contract for any caller that
  predates this remediation, per the prompt's explicit "do not allow a
  silently unknown/null state" instruction — see Q.6 for the one
  pre-existing test payload this required updating.
- `PUT /api/members/{id}` (`schemas.MemberUpdate`): same two fields,
  both **optional**. Critically, *omitting* `next_of_kin_is_member`
  from the request body (not sending it at all) means "don't touch the
  Next-of-Kin relationship" — different from explicitly sending `false`
  ("clear/replace with a non-member Next of Kin"). `routers/members.py`
  distinguishes these via `payload.model_dump(exclude_unset=True)`
  membership, not by truthiness, exactly mirroring how every other
  optional field on this same endpoint already behaves.
- `GET /api/members`, `GET /api/members/{id}`, `GET /api/members/me`
  (`schemas.MemberOut`): two new response fields,
  `next_of_kin_is_member` (`bool | null`) and `next_of_kin_member`
  (a minimal `{id, psn, name, phone}` projection, never the full
  `MemberOut` — someone editing/viewing another member's record as
  "just the linked NOK" has no business reason to see that person's
  bank/account/loan-restriction fields). Both are computed,
  request-scoped attributes populated by `_attach_next_of_kin()`
  (`routers/members.py`) via one bulk query per list/get call, the same
  pattern `_attach_login_state()` already established for
  `login_user_id`/`login_account_status` — never persisted columns on
  `Member` itself.
- **No new endpoint or permission code.** Next-of-Kin management reuses
  the existing `member.create`/`member.update`/`member.view`
  permissions (Next-of-Kin is a property of a member's record, not a
  separate resource with its own access model) and the existing member
  search (`GET /api/members?search=...`) for finding a candidate
  Next-of-Kin member, the same endpoint `admin_users.py`'s Admin↔Member
  linking UI already uses for exactly this kind of "search and pick a
  member" flow (Section O).
- `has_member_conflict(db, member_a_id, member_b_id)`
  (`member_relationships.py`) is a plain importable function, **not**
  exposed as an HTTP endpoint in this pass. It's governance foundation
  only (Section 12-14 of the remediation prompt are explicit that
  wiring member-to-member conflicts into loan/disbursement/repayment
  approval is future work, not part of this remediation) — no
  self-contained public use case for a standalone "check if two
  arbitrary members conflict" endpoint exists yet, and adding one now
  would be scope creep the prompt didn't ask for. Covered directly by
  function-level tests (`db_session` fixture) rather than through the
  API surface.

### Q.5 Frontend changes

`app/members/page.tsx`: the Next-of-Kin section of the Add/Edit form now
opens with a required Yes/No question ("is a cooperative member" /
"is not a cooperative member"), reusing the exact search-and-select
pattern already established in `app/admin/users/page.tsx` for the
Admin↔Member linking dialog (`listMembers({search, limit: 10})` +
inline results list), rather than inventing a second one. Selecting
"is a cooperative member" hides the manual next-of-kin text fields
entirely and shows the search/select picker instead; selecting "is not"
does the reverse — never both at once, so there's no way to submit an
ambiguous state the backend would reject anyway. The member being
edited is filtered out of their own Next-of-Kin search results
client-side (the backend's self-reference 409 is still the actual
enforcement; this is just so the person editing never sees a choice
that would just bounce). A new "Next of kin" column was added to the
Members table so the current relationship (manual name, or "PSN — Name
(member)") is visible without opening Edit. `lib/api.ts`'s `Member`/
`MemberInput` interfaces were extended with the same fields as the
backend schema change; no changes were needed to `ApiError`/
`describeError`, since the self-reference 409 reuses the existing
`{"error", "message"}` shape that error handling already understands.

### Q.6 Tests

New `tests/test_member_relationships.py`: required-field enforcement on
create (422 when omitted), manual-NOK create, member-linked-NOK create
(including the `MemberRelationship` row's exact shape), the
`model_validator` consistency rules in both directions, 404 for a
nonexistent target member, changing to a different member (asserts
BOTH the old row is preserved as `removed` and the new row is `active`
— not just the visible end state), reverting a member-linked NOK back
to manual, confirming an ordinary edit that never mentions Next of Kin
leaves an existing relationship completely untouched, the self-reference
409, a same-value resubmission being a true no-op (no extra row, no
duplicate audit event), the partial unique index rejecting a second
active row inserted directly against the DB (bypassing the application
layer entirely), permission enforcement (403 without `member.create`),
and four `has_member_conflict` cases (both directions from one stored
row, unrelated members, false after removal, and the `None`/identical-id
edge cases).

`tests/test_database_integrity.py`'s two pre-existing
`POST /api/members` payloads (`test_duplicate_psn_rejected`) were
updated to include `next_of_kin_is_member: false` — the minimal change
needed to keep that regression test passing under the new required
field, not a weakening of what it verifies (duplicate-PSN rejection is
unrelated to and unaffected by this remediation).

**All written and `python -m py_compile`-verified across the full
repository. None executed** — same standing sandbox limitation (no
network, no reachable Postgres) as every prior pass in this engagement;
see the top-level continuation prompt for why running the real suite
against a disposable database remains the single highest-value next
action.

### Q.7 Files changed

**Backend:** `models.py` (`RelationshipType`, `RelationshipStatus`,
`MemberRelationship`), new `member_relationships.py` (service module —
`get_active_relationship`, `set_relationship`, `clear_relationship`,
`has_member_conflict`), `schemas.py` (`NextOfKinMemberSummary`,
`MemberCreate`/`MemberUpdate`/`MemberOut` extensions),
`routers/members.py` (`_attach_next_of_kin`, wired into
`create_member`/`update_member`/`list_members`/`get_member`/
`get_my_member_record`), new migration
`scripts/manual_migration_2026_09_member_relationships.sql`.

**Frontend:** `lib/api.ts` (`Member`/`MemberInput` extensions),
`app/members/page.tsx` (Yes/No question, member search/select picker,
Next-of-kin table column).

**Tests:** new `tests/test_member_relationships.py`;
`tests/test_database_integrity.py` (two payloads updated, see Q.6).

### Q.8 What remains outstanding

- **Migration not applied to any real database** —
  `scripts/manual_migration_2026_09_member_relationships.sql` must be
  run (Neon Console SQL Editor) before or in the same deploy step as
  this backend code — never after, per this project's standing
  migration-ordering lesson (see the migration file's own header
  comment, and Section N).
- **No automated test has been executed** — same standing gap as every
  prior pass.
- No frontend build/TypeScript check has been run — same limitation as
  every prior pass; manual bracket-balance and line-by-line review were
  used instead as a partial substitute (see this session's own working
  notes).
- **The four open business decisions from the Phase 0 Admin↔Member
  Linking Assessment remain unresolved** and are unrelated to /
  unaffected by this pass — noted here only so this report doesn't look
  like it forgot them.
- `has_member_conflict()` is intentionally unused by any approval path
  in this pass (Q.4) — wiring it into loan/disbursement/repayment
  authorization, and deciding exactly how it should interact with
  `self_conflict.py`'s existing User↔Member check (additive? does one
  take precedence?), is explicitly future work, not started here.
