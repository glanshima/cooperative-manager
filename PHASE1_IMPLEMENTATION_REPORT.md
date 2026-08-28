# MACT Cooperative Manager — Phase 1 Implementation Report

**Phase:** 1 — Security, Authorization, Audit & Data Integrity Foundations
**Date:** 2026-08-28 (implementation), 2026-08-28 (remediation pass, this update)
**Status:** **PHASE 1 — NOT YET VERIFIED.** Code-level remediation is complete (see Section J below).
The blocker is entirely environmental: the remediation pass ran in a sandboxed
container with no outbound network access and no reachable PostgreSQL instance
(confirmed by direct attempts — see Section J.5), so the backend test suite,
the frontend production build, and the disposable-database migration
verification that Sections 9–11 of the remediation prompt require could not
be executed. Every fix below was verified the strongest way this environment
allows (full manual code inspection + `python -m py_compile` on every backend
file), but that is not the same thing as a green test run, and this report
says so explicitly rather than claiming otherwise. Section J gives the exact
commands to run outside this sandbox to close out verification.

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
