# Running the Phase 1 test suite

These tests were written but **not executed** in the environment this
implementation was produced in (no network access, so `pip install` for
FastAPI/SQLAlchemy/pytest/httpx could not run, and no Postgres instance was
reachable). Run them for real before merging Phase 1.

## Setup

```bash
cd backend
python -m venv .venv && source .venv/bin/activate      # or your usual venv approach
pip install -r requirements-dev.txt

export DATABASE_URL="postgresql://user:pass@host/mact_test"   # a DISPOSABLE test DB/branch -- never point this at real cooperative data
export SECRET_KEY="test-only-secret"

pytest -v
```

A disposable Neon branch works well for `DATABASE_URL` here (Neon branches
are cheap and isolated). The suite creates all tables via
`Base.metadata.create_all` on first run and wraps every test in a
transaction that's rolled back afterward, so the same test database can be
reused across runs without manual cleanup.

## What's covered

- `test_auth.py` -- login (valid/invalid/unknown username), brute-force
  lockout, deactivated-account login rejection, **immediate** loss of
  access on an already-issued token when the account is deactivated
  mid-session, password policy enforcement, logout/session revocation.
- `test_authorization.py` -- permission-gated endpoints, super-admin
  bypass, role revocation taking effect immediately, and the
  loan.approve/loan.reject segregation-of-duties split.
- `test_idor.py` -- ID-substitution attempts across members and loans,
  admin access without the relevant `*.view` permission, and 404-vs-403
  behavior for non-existent IDs.
- `test_audit.py` -- audit events are written for auth and business
  actions, actor is correctly attributed, passwords never appear in
  audit payloads, and the audit endpoints themselves are
  permission-gated.
- `test_database_integrity.py` -- duplicate PSN/username rejection, and
  the financial-history-protection behavior for members (block only when
  linked loans/applications exist) and loans (never deletable).
- `test_idempotency.py` -- repeated repayment-verification requests with
  the same `Idempotency-Key` don't double-credit a loan, a reused key
  with a different body is rejected (409), and re-verifying an
  already-reviewed repayment without a key at all is still blocked by
  the underlying status/row-lock guard.

## What's NOT covered yet (see the implementation report, Section H)

- Concurrency under genuine parallel requests (these tests exercise the
  *logic* of the row-lock/status-guard path sequentially; a true
  multi-threaded/multi-connection race test is still worth adding).
- Disbursement end-to-end (loan creation + balance deduction across
  multiple active loans) beyond what's implied by the idempotency test.
- Frontend component/integration tests (none exist for this project yet,
  Phase 1 or otherwise).
- Rate limiting at the HTTP layer (the brute-force *lockout* is tested;
  a broader per-IP rate limiter was not implemented in Phase 1 -- see
  the implementation report).
