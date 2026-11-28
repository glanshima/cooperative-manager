# MACT Cooperative Manager — Controlled Remediation Pre-Implementation Assessment

**Assessment date:** 2026-11-27 (refreshed after the merged loan-workflow release)

**Phase:** Phase 0 — Approved implementation baseline

**Controlling prompt:** `D:\desktop\Koppera prompts\MACT Cooperative Manager.md`

**Branch:** `feature/mact-controlled-remediation-a-i`

**Base commit:** `a62320c59c0b384f4f7e066fae55d1bb0fcc7688`

## 1. Executive conclusion

The repository already contains most of the architectural foundations required by the controlled remediation: permission-based administration, conflict-of-interest controls, database-backed notifications, auditable financial workflows, revocable JWT sessions, hashed password-recovery tokens, a double-entry Cashbook, Vercel Blob storage, shared UI primitives, and local regression suites.

The universal loan-fee and staged-application slice was merged as `a62320c59c0b384f4f7e066fae55d1bb0fcc7688` and its production schema migration was applied and verified on 2026-11-27. That completed slice must not be reimplemented: one canonical fee, frozen approval terms, no second fee for application-derived loans, staged member/admin review, and Cashbook posting when books are enabled and open already exist.

The remaining A–I work is approved for implementation on `feature/mact-controlled-remediation-a-i`. No workstream is fully compliant end to end, and implementation must extend the existing systems rather than replace them.

| Workstream | Overall status | Short finding |
|---|---|---|
| A — Repayment submission notifications | **Partially implemented** | Submission and verification are financially safe, but submission emits no staff notice or audit event and has no retry idempotency. |
| B — Savings increase-request consistency | **Defective** | Backend eligibility is correct; the dashboard hides the request action from eligible financial members whose amount is not yet set. PSN 32100 account state was not accessed. |
| C — First-login credential delivery | **Missing** | Existing recovery primitives are reusable, but the approved 30-minute email setup flow and server-generated 24-hour temporary-password flow do not exist. |
| D — Independent balance visibility | **Missing** | Balances render unconditionally; there are no independent visibility controls or shared visibility state. |
| E — Password visibility | **Partially implemented** | All eight current password inputs are hidden by default, but none has an independent show/hide control. |
| F — Session timeout and authentication security | **Defective** | The JWT plus `AuthSession` foundation exists, but idle enforcement, the approved eight-hour policy, continue-session, activity classification, and multi-tab coordination are missing. Session validation is fail-open in important respects. |
| G — Loan lifecycle and Cashbook receipts | **Partially implemented** | The loan-fee/staged-application release is complete. Remaining defects are cancellation/reschedule races, terminal payment-status handling, unavailable-book verification, missing historical admin views, and the disbursement count. |
| H — Member profile pictures | **Missing** | No photo schema, API, upload flow, or display integration exists. The current monogram fallback is also incorrect. |
| I — Notification-panel close control | **Partially implemented** | Escape and outside-click closing work without read-state mutation, but there is no visible close control. |

No A–I application-code implementation has begun in this branch. No push, merge, deployment, production settings change, or new production migration is authorized for A–I.

## 2. Repository identity and working-tree state

| Item | Verified value |
|---|---|
| Repository | MACT Cooperative Manager / `cooperative-manager` |
| Remote | `https://github.com/glanshima/cooperative-manager.git` |
| Current branch | `feature/mact-controlled-remediation-a-i` |
| Current commit | `a62320c59c0b384f4f7e066fae55d1bb0fcc7688` |
| Branch base | `origin/main` at `a62320c59c0b384f4f7e066fae55d1bb0fcc7688` |
| Completed prerequisite release | `46246affd1849bd9a4ef21b92329051d26ed0feb`, merged as `a62320c` with identical tree |
| Working-tree changes at refresh | `frontend/tsconfig.tsbuildinfo` modified; this assessment untracked |
| Nature of generated cache change | Pre-existing TypeScript build cache; deliberately untouched and excluded from implementation staging |
| A–I application files changed | None |
| New A–I commits | None |
| A–I push/merge/deployment/production changes | None |

The repository root is the established documentation location: it already contains `implementation-report.md`, `PHASE1_IMPLEMENTATION_REPORT.md`, `PASSWORD_RECOVERY_IMPLEMENTATION_REPORT.md`, and other controlled-remediation reports. There is no `docs/` directory, so the required remediation reports belong in the repository root.

## 3. Architecture findings

### 3.1 Application stack

- **Frontend:** Next.js 16.4.6, React 18.3.1, TypeScript 5.5.4, CSS Modules, shared design tokens, Vitest 5.1.0, React Testing Library, jsdom.
- **Backend:** FastAPI 0.115.0, Pydantic 2.9.2, SQLAlchemy 2.0.35, Python, JWT via PyJWT, bcrypt via Passlib.
- **Database:** PostgreSQL. Production uses Neon; local verification uses embedded PostgreSQL at `127.0.0.1:55432`, with `mact_local` for seeded browser data and `mact_test` for pytest.
- **Deployment:** Independently hosted frontend/backend projects on Vercel with a shared PostgreSQL/Neon database per deployment. Cooperative-specific configuration remains independent.
- **File storage:** Vercel Blob is already used for cooperative branding logos. Local disk is not the deployment persistence layer.

### 3.2 Governance and authorization

The established model remains:

`User → Office/Position → Role → Permissions`

Important controls already present:

- Backend enforcement through `require_admin`, `require_member`, `require_permission`, and `require_any_permission`.
- Multiple active role assignments per user.
- Optional office/position assignment.
- `Role.requires_member_link` enforcement for applicable roles.
- Active role, active assignment, and active permission checks.
- Super-admin bypass is explicit; it does not replace the permission catalogue.
- Next-of-kin conflict-of-interest checks on reads and writes.
- Frontend permission filtering is presentation only, not the security boundary.

No redesign of User Management, roles, offices, positions, or multi-tenancy is proposed.

### 3.3 Authentication and sessions

The existing architecture is JWT access tokens plus server-side `AuthSession` rows:

- JWT claims: `sub`, `role`, `exp`, `jti`.
- `AuthSession` stores `jti`, `user_id`, `issued_at`, `expires_at`, IP/user-agent metadata, and revocation fields.
- Logout revokes the current session.
- Password change revokes other sessions.
- Password recovery and staff reset revoke all sessions.
- Account suspension/deactivation is rechecked on each authenticated request.
- Password hashing uses bcrypt.
- Password policy requires a configurable minimum length, at least one letter, and at least one number.
- Account lockout exists after repeated failed logins.
- `PasswordResetToken` stores only a SHA-256 token hash and supports expiry, attempt limits, single use, and row-locked reset.

This is the correct foundation for Workstreams C, E, and F. A second authentication system is neither needed nor permitted.

### 3.4 Notifications and audit

- Notifications are database rows created inside the same transaction as the business event they announce.
- `notify`, `notify_member`, and `notify_staff` already exist.
- Staff notifications are permission-scoped rather than broadcast to every administrator.
- Notification preferences and email gating already exist.
- The frontend notification bell polls and supports explicit read actions.
- The audit service records structured before/after values, actor, action, entity, reason, and request metadata.
- Existing authentication paths avoid recording plaintext passwords or raw recovery tokens.

Workstream A should reuse this architecture. Workstream I is a frontend-only close-control change.

### 3.5 Financial workflows and Cashbook

Existing financial controls already include:

- Pending/unverified repayment submission separate from verification.
- Permission-gated, row-locked, idempotent repayment verification.
- Savings change requests with minimum amount, eligibility, duplicate-pending prevention, approval/rejection permissions, and next-month effective dates.
- Staged member loan application: request, terms/payout, fee payment, review/submit.
- Staged admin loan review: verify payment, approve/reject, disburse.
- One canonical application/loan fee, snapshotted on application and loan, excluded from all loan mathematics.
- Frozen approval terms with legacy fallback, application-derived fee-settlement marker, and duplicate fee-obligation trigger.
- Verified application-fee Cashbook posting through the existing `LOAN_FEE` source and application UUID when Cashbook is enabled and open.
- Cancellation and rescheduling with retained payment evidence, but without the required row locking/idempotency/audit on reschedule.
- Double-entry Cashbook accounts, balanced immutable journal entries, period locks, reversals, and unique `(source, source_id)` posting identity.
- Existing automatic postings for disbursement, repayment, loan fees, savings settlement, payroll deductions, and dividends.

The controlling prompt says not to introduce a full double-entry accounting system. That instruction is compatible with the current repository only if interpreted as **do not replace or expand the accounting architecture**. Workstream G must reuse the existing Cashbook posting foundation and stable `LOAN_FEE` identity; it must not create a second ledger or chart of accounts.

### 3.6 Migrations and tests

- The project does not actively use Alembic.
- `Base.metadata.create_all()` creates missing tables but does not add missing columns.
- Schema changes require ordered, idempotent files in `scripts/manual_migration_*.sql`.
- New migrations must be registered in `ORDERED_MIGRATIONS` in `scripts/apply_manual_migrations.py`.
- Local migration execution defaults to the sandbox and requires `--allow-remote` for non-sandbox targets.
- Backend pytest uses a real disposable PostgreSQL database and per-test rollback.
- Frontend Vitest uses jsdom and React Testing Library.
- Existing local gates are documented in `LOCAL_TESTING_AND_PRE_PUSH.md`.

No migration was executed as part of the Phase 0 reassessment. The separately authorized production loan-workflow migration was applied and verified before this branch was created.

## 4. Compliance matrix

Status meanings follow the controlling prompt:

- **Already compliant:** the approved behavior exists and no remediation is required.
- **Partially implemented:** substantial approved behavior exists, but one or more required pieces are absent or defective.
- **Defective:** the workflow exists but has a correctness, security, or consistency defect.
- **Missing:** the approved workflow or capability does not exist.

| Workstream | Overall | Already compliant | Missing or defective | Approved implementation decision |
|---|---|---|---|---|
| A | Partially implemented | Pending repayment state; ownership and active-loan checks; no automatic financial effect; permission-gated, row-locked, idempotent verification; Cashbook posting and audit on verification | No submission notification; no submission audit; no submission idempotency; notification recipient account-status gap; verifier queue-access mismatch | Narrow pending queue/evidence access for `repayment.verify`; retry idempotency only, with legitimate multiple repayments allowed |
| B | Defective | Financial-member eligibility; settings minimum; self-service identity; pending-request uniqueness; approval/rejection permissions; next-month effective date; admin cannot directly replace approved amount | Dashboard suppresses the action when the current amount is falsy; contradictory frontend test; request-history failures can be silently swallowed | No PSN special case; fix generic NULL state. Account-level state remains unverified because no authorised access was performed |
| C | Missing | Reusable bcrypt policy, lockout foundation, hashed recovery token, row-locked single-use recovery, session revocation patterns, existing `/change-password` page | No admin-initiated 30-minute setup link; no replacement invalidation at issuance; no delivery status; no server-generated 24-hour temporary password; no one-time display/Copy; no universal backend password-change gate | Token-aware `/change-password`; `PENDING` until setup; persisted delivery status; 24-hour temporary credentials; legacy forced reset; PostgreSQL-backed limits |
| D | Missing | Balances are visible by default; financial authorization remains correctly backend-scoped; no financial amounts are stored in browser storage | No per-balance state, controls, masking, shared visibility context, or tests | Session-only; savings, loan, deduction/contribution balances and derived comparisons; historical amounts remain visible |
| E | Partially implemented | All eight current password inputs use `type="password"`; no inspected code logs password values | No show/hide controls; no reusable password input; no independent visibility state; autocomplete/labels incomplete; member temporary-password prompt is unmasked | Reusable accessible field shared by current and first-login fields |
| F | Defective | Authenticated database user determines role; JWT signature/expiry validation; session revocation; account-status recheck; one existing session architecture | No idle timestamps or enforcement; no approved eight-hour policy; no meaningful-activity definition; no polling exclusion; no continue-session; missing session rows accepted; `AuthSession.expires_at` ignored; session/user binding not checked; no multi-tab coordination | Eight-hour absolute; 15-minute admin/30-minute member idle; explicit interaction/Continue only; shared across tabs; five-minute warning; legacy sessions reauthenticate |
| G | Partially implemented | Universal fee, snapshots, frozen approval terms, no second fee, staged review, Cashbook posting when enabled/open, direct-fee concurrency, duplicate trigger, verified production migration | Cancellation/reschedule locking; cancellation idempotency; reschedule audit; terminal payment-status semantics; disabled-book receipt policy; historical admin views; disbursement count | Block verification when books disabled/unopened/locked; allow terminal payment review without status overwrite; no historical Cashbook backfill |
| H | Missing | Existing Vercel Blob client; raster allowlist and magic-byte detection baseline; preview pattern; permission/audit patterns; structured last-name field | No photo field, migration, API, upload UI, ownership checks, dimension validation, display propagation, deletion lifecycle, or broken-image fallback; current monogram logic is wrong | Authenticated-only delivery; JPEG/PNG/WebP; 5 MB input; 2048 px maximum; admin `member.update` plus COI guard |
| I | Partially implemented | Escape closes and restores focus; outside click closes; opening only refreshes; read mutations require explicit actions; backend mutation routes are user-scoped | No visible close button; no test proving close leaves read state/count/mutation APIs untouched; panel focus semantics incomplete | Add visible close using existing non-mutating helper and focus restoration |

## 5. Detailed findings

### Workstream A — Repayment submission notifications

**Current compliant behavior**

`backend/app/routers/loan_repayments.py:46-92` creates a `LoanRepayment` in `AWAITING_VERIFICATION`. It validates member role, ownership, active loan status, positive amount, payment month, and receipt evidence. It does not verify the repayment, change `Loan.amount_repaid`, complete the loan, or post to Cashbook.

`backend/app/routers/loan_repayments.py:193-367` performs verification under `repayment.verify`, locks the repayment and loan rows, checks conflict-of-interest rules, posts to Cashbook, updates balances, notifies the member, and audits the result. The existing idempotency foundation is already used on verification.

**Defects and gaps**

1. Submission calls `db.commit()` without creating a staff notification.
2. Submission has no audit event.
3. Submission does not use the existing `Idempotency-Key` foundation, so a retry can create another repayment and, once notifications are added, another notice.
4. `notify_staff` filters `User.is_active` but not `account_status == ACTIVE` (`backend/app/notification_service.py:79-115`). The lifecycle service normally mirrors these fields, but the notification contract should independently enforce active account status.
5. Queue reads require `repayment.view`, while verification requires `repayment.verify` (`backend/app/routers/loan_repayments.py:130-175,193-203`). A custom verifier without `repayment.view` could receive a notice but be unable to open the evidence.
6. There is no natural database uniqueness rule for repayment submissions. Multiple legitimate repayments for one loan/month may be valid, so a business duplicate rule must not be invented.

**Proposed correction**

- Queue the staff notice inside the submission transaction using `notify_staff(permission_code="repayment.verify", ...)`.
- Link to `/admin/loan-repayments?status=awaiting_verification`.
- Add a submission audit event without receipt contents or secrets.
- Apply the existing idempotency foundation to submission and send a stable per-attempt key from the frontend.
- Filter staff recipients by both active flag and active account status.
- Preserve `repayment.view` as the general read/history boundary. Add a narrowly scoped pending-verification queue/detail authorization for `repayment.verify`, or notify only verifiers who also hold `repayment.view`; do not broadly grant verifiers access to all repayment history.
- Do not add loan/month/amount uniqueness unless the owner explicitly defines a business duplicate rule.

### Workstream B — Savings increase-request consistency

**Verified repository-level root cause**

The backend intentionally permits a financial member with no amount on file to submit an initial/increased request. This is asserted by `backend/tests/test_contribution_changes.py:303-309`.

The frontend contradicts that rule. `frontend/components/dashboard/ContributionCard/index.tsx:62-64` reads the status and amount, and `:126-136` returns early when `amount` is falsy. That early return removes the request button and tells the member to contact an officer. The current frontend test explicitly expects the defective behavior at `frontend/components/dashboard/ContributionCard/index.test.tsx:92-100`.

If PSN 32100 is a financial member with `monthly_contribution_amount = NULL`, this defect fully explains the reported symptom. No PSN-specific logic exists.

**Already compliant backend behavior**

- Only financial members are eligible.
- The minimum comes from cooperative settings.
- Self-service requests use the authenticated member.
- Requests must meet the minimum, differ from the current amount, and have no pending request.
- A partial unique index enforces one pending request.
- Approval/rejection is permission-gated and row-locked.
- Approved changes apply from the first of the following month.
- Admin member editing cannot directly replace or clear the approved amount.

**Secondary frontend risk**

`loadRequests()` uses `Promise.allSettled`, but its outer `catch` cannot catch individual rejected promises. If request-history loading fails, the UI can silently behave as though no pending request exists. The backend remains authoritative, but the member receives a confusing experience.

**Proposed correction**

- Remove the falsy-amount early return.
- Render a clear “not yet set” amount state while retaining the request action for financial members.
- Handle `NULL` safely in the modal and history display.
- Preserve pending-request disabling, minimum validation, and next-month messaging.
- Surface request-history loading errors without hiding the action solely because savings loading failed.
- Replace the contradictory test with coverage for a financial member whose amount is `NULL`.
- Do not add PSN 32100 special-case logic.

**Account-level limitation**

No authorised access to PSN 32100 was performed. Financial classification, current amount/backfill state, existing pending requests, and API response history remain unverified account-level observations.

### Workstream C — First-login credential delivery

**Current state**

`backend/app/routers/auth.py:203-279` creates a member login from an administrator-supplied temporary password. The frontend uses an unmasked `window.prompt` at `frontend/components/members/hooks/useMembersPage.ts:473-486`. There is no server-side generation, 24-hour expiry, one-time display, Copy action, or delivery record.

The existing recovery flow at `backend/app/routers/auth.py:472-515` is a useful primitive, but it is self-service recovery, not administrator-initiated first-login setup. It uses a configurable 15-minute default, does not invalidate older pending links when a replacement is issued, and only logs email failure.

`PasswordResetToken` (`backend/app/models.py:947-970`) stores a secure hash, expiry, use time, and attempt count, but has no token purpose or delivery status.

**Security defects relevant to C**

- `must_change_password` is not a global backend gate. `require_password_already_changed` exists (`backend/app/deps.py:81-94`) but is not applied to all authenticated routes.
- A setup-link user has no current password, while the existing `/change-password` page/API requires one (`frontend/app/change-password/page.tsx:59-79`; `backend/app/routers/auth.py:132-184`).
- Member password reset replaces the hash but does not revoke existing sessions (`backend/app/routers/auth.py:282-336`).
- Failed-login increments are not row-locked, and the failure count is not reset when a lockout expires (`backend/app/account_lifecycle.py:31-47`).
- A locked valid account receives an explicit 423 response before password verification, revealing account existence (`backend/app/routers/auth.py:42-54`).
- Login has no IP/global limiter; credential issuance has no limiter.

**Proposed correction**

- Extend the existing token model with an explicit purpose, delivery status, issuing administrator, and replacement/use metadata. Preserve existing recovery rows with a backward-compatible purpose default.
- Create a 30-minute, single-use, hashed setup-token flow for members with valid email.
- Invalidate older setup tokens when a replacement is issued.
- Persist email delivery outcome and return an administrator-visible success/failure status. Never fall back to a temporary password after email failure.
- Make the existing `/change-password` page token-aware rather than creating a separate password-management workflow. A valid setup token authorizes setting the first password without requiring a current password.
- Generate temporary passwords server-side for members without email, store only the hash plus issuance/expiry metadata, return the plaintext once, and display it in an accessible modal with Copy and explicit dismissal.
- Enforce the 24-hour expiry at login and invalidate the previous credential on replacement.
- Apply the forced-password-change gate at the backend authentication boundary, with only the setup/change endpoints exempt.
- Revoke sessions on member password reset and replacement.
- Add database-backed rate limiting suitable for serverless/multi-instance deployment and remove account-existence leakage from locked/inactive login responses.
- Audit issuance, replacement, delivery failure, setup completion, expiry, and rejection without recording secrets.

### Workstream D — Independent financial-balance visibility

**Current state**

Principal balances render unconditionally in:

- `frontend/components/dashboard/SummaryCards/index.tsx`
- `frontend/components/dashboard/AccountOverview/index.tsx`
- `frontend/components/dashboard/ContributionCard/index.tsx`
- `frontend/components/dashboard/MembershipCard/index.tsx`
- `frontend/components/dashboard/LoansSection/index.tsx`

No visibility state, control, preference field, or storage key exists. Browser storage currently contains the authentication token and table page-size preference, not financial amounts.

Backend authorization is already correct: member savings/deductions are scoped through `current_user.member_id`, and loan reads enforce self-access or `loan.view`. This workstream can remain presentation-only.

**Design risks**

- Hiding only the summary card is insufficient; the same balance appears in multiple components.
- Comparison bars and “savings cover your loan balance” text can disclose financial relationships even when the numeric value is masked.
- Hidden values must not remain in accessible names, titles, screen-reader text, or DOM text.
- Controls need meaningful names, state, keyboard operation, and adequate mobile touch targets.

**Proposed correction**

- Add a dashboard visibility context with independent state for savings, loans, and deductions/contribution balances.
- Default every category to visible.
- Use the same state for every repeated representation of a balance.
- Mask the value and suppress or neutralise derived bars/ratios when hidden.
- Keep visibility session-only unless the owner approves persistence. If persisted, store only boolean visibility settings, never amounts.
- Do not change backend permissions or financial calculations.

### Workstream E — Password visibility

A complete search found exactly eight current password inputs:

- `frontend/app/login/page.tsx:55`
- `frontend/app/change-password/page.tsx:62,69,76`
- `frontend/app/reset-password/page.tsx:131,143`
- `frontend/components/admin-users/CreateStaffForm/index.tsx:37`
- `frontend/components/admin-users/ResetPasswordRow/index.tsx:32`

All are hidden by default. None has a show/hide control. Several rely on placeholders rather than explicit labels, and none specifies `current-password` or `new-password` autocomplete.

The member temporary-password `window.prompt` is also unmasked and cannot support an independent eye control.

**Proposed correction**

- Add one reusable accessible `PasswordInput` component.
- Keep `type="password"` by default.
- Give each field independent visibility state.
- Use a `type="button"` eye/eye-off control with a meaningful label and pressed state.
- Preserve the field value and never submit the form when toggling.
- Preserve appropriate `autocomplete` values.
- Replace all eight inputs and any first-login setup fields added under C.
- Replace the member prompt with the approved one-time credential modal.
- Add tests for hidden default, independent toggles, value preservation, keyboard operation, and no form submission.

### Workstream F — Session timeout and authentication security

**Verified defects**

`backend/app/deps.py:18-66` decodes the JWT and loads the user, but:

1. It rejects a session only if a matching row exists and `revoked_at` is set.
2. It accepts a valid signed token if no matching `AuthSession` row exists.
3. It does not check `AuthSession.expires_at`.
4. It does not check `session.user_id == user.id`.
5. It has no last-activity or idle-deadline check.

The `AuthSession` docstring says validation checks that the session is unrevoked and unexpired, but the implementation does not enforce expiry (`backend/app/models.py:914-939`).

`backend/app/auth.py:17,30-38` defaults access tokens to 120 minutes and uses the same deadline for JWT expiry and `AuthSession.expires_at`. Runtime override values were not inspected.

Notification polling runs on mount and every 60 seconds. The shared API wrapper has no automatic retry today, but there is no activity-exclusion contract for future retries.

**Proposed correction**

- Add `last_activity_at` to `AuthSession`; retain `expires_at` as the immutable eight-hour absolute deadline.
- Set both JWT expiry and session absolute expiry to eight hours at login, but only after matching-session, absolute-expiry, and idle checks are enforced; lengthening JWTs first would weaken the current security posture.
- Determine idle duration from the authenticated database user role: 15 minutes for admins, 30 minutes for members.
- Require a matching session row for all new tokens carrying `jti`; validate user binding, revocation, absolute expiry, and idle expiry. Preserve bounded legacy-token behavior only where required for compatibility.
- Define meaningful activity as explicit user interaction or an explicit continue-session action. Do not auto-renew on arbitrary API calls.
- Add a backend-validated continue-session endpoint that locks the session, rejects expired/revoked sessions, updates only `last_activity_at`, and never changes the absolute deadline.
- Ensure notification polling, automatic refresh, and retries never call continue-session.
- Add frontend warning/countdown and Continue action using server-provided deadlines.
- Synchronize expiry/logout across tabs through a browser channel/storage event while keeping the database session as the authority.
- Revoke expired sessions with a reason instead of leaving them silently reusable.
- Update test fixtures to create real `AuthSession` rows rather than relying on fail-open missing-session acceptance.

### Workstream G — Remaining loan lifecycle and Cashbook policy gaps

**Completed baseline: do not reimplement**

Commit `46246affd1849bd9a4ef21b92329051d26ed0feb`, merged as `a62320c`, delivered:

- One canonical `Settings.loan_form_fee` for every new application and direct loan.
- Application and direct-loan fee snapshots excluded from payout, principal, interest, total repayable, and instalments.
- Four-step member application and three-gate admin review/disbursement workflow.
- Frozen approval rate, interest mode/spread, amount, tenure, and fee snapshot, with legacy disbursement-date fallback.
- `Loan.fee_paid_via_application` plus a database trigger preventing duplicate pending/verified fee obligations for application-derived loans.
- Verified application-fee posting through the existing Cashbook `LOAN_FEE` source keyed by application UUID.
- Direct-fee row locking, stale-ORM refresh, and duplicate protection.
- Additive production migration applied and verified on 2026-11-27.

**Remaining defects and gaps**

1. Cancellation and reschedule read the application without a row lock, so they can race approval, payment verification, or disbursement.
2. Cancellation has no idempotency dependency; duplicate concurrent requests can duplicate notifications and audit events.
3. Rescheduling has no audit event.
4. Payment verification currently ignores terminal application status. Rejecting payment can overwrite `CANCELLED` with `REJECTED`.
5. `cashbook.post_application_fee` silently returns `None` when the Cashbook module is disabled. Enabled-but-unopened or locked books already block posting.
6. The admin UI lacks dedicated Rejected and Cancelled historical views and can include cancelled applications in the default active queue.
7. The dashboard approved-awaiting-disbursement count filters only `status == APPROVED`, not `resulting_loan_id IS NULL` (`backend/app/dashboard.py:339-350`).
8. Existing cancellation policy remains correct: pending applications can be cancelled; approved applications only before a resulting loan exists; disbursed/rejected/cancelled applications are not cancellable; fee is non-refundable; evidence is retained; rescheduling creates no fee.

**Approved correction**

- Row-lock cancellation and rescheduling and make cancellation retry-idempotent.
- Add a reschedule audit event.
- Allow payment evidence review after cancellation/rejection without changing the terminal application status. Approved verification creates the receipt; rejected verification retains evidence and the terminal state.
- For a positive fee, block verification whenever the Cashbook module is disabled, unopened, or the period is locked. Preserve zero-fee no-op behavior.
- Add Pending, Approved/awaiting disbursement, Rejected, Cancelled, and All admin views; exclude cancelled applications from the default active queue.
- Correct the approved-awaiting-disbursement count.
- Reuse the existing `LOAN_FEE` posting and unique `(source, source_id)` identity. Never reverse/delete receipts on cancellation/rejection and never backfill historical verified fees automatically.

### Workstream H — Member profile pictures

**Current state**

No profile/photo/avatar field exists on `Member`, and no photo API, migration, upload flow, or tests exist. The only current avatar is the dashboard monogram.

The monogram implementation is defective. `frontend/components/dashboard/MemberShell/index.tsx:28-34` takes the first letters of the first two ASCII words of the full printed name. It ignores the structured last name and can produce the wrong result for family-first display names.

**Reusable foundations**

- Vercel Blob upload/delete client: `backend/app/blob_storage.py`.
- PNG/JPEG/WebP allowlist and magic-byte detection: `backend/app/validation.py:161-192`.
- Object-URL preview and cleanup: `frontend/components/admin-settings/BrandingSection/index.tsx`.
- Existing permission, audit, replacement, and deletion-failure patterns in branding settings.

**Important limitations**

- Existing branding validation checks signatures only; it does not decode images or enforce dimensions.
- No backend image-processing/dimension library is currently declared.
- Branding Blob URLs are public. That may or may not be acceptable for member photos.
- Receipt storage is not reusable: it permits PDF/HEIC and stores base64 in database columns.
- Adding a URL only to `MemberOut` would not propagate photos to nested member summaries used by loans, applications, deductions, disbursements, and linked-member displays.

**Proposed correction**

- Add an additive migration for an internal photo URL reference; do not store base64 image payloads in PostgreSQL.
- Use the established Vercel Blob deployment storage, subject to the owner’s privacy decision.
- Decode and re-encode accepted raster images server-side; enforce format, byte-size, and pixel-dimension limits; reject SVG and executable content.
- Generate safe server-side filenames and derive the blob to delete from stored server data, never a client-supplied URL.
- Enforce member ownership for self-service management.
- Require `member.view` for admin photo visibility and `member.update` plus conflict-of-interest checks for admin replacement/deletion, subject to owner approval.
- Add upload, preview, save, replace, and delete UI.
- Add a reusable avatar component that uses the first letter of `last_name`, handles Unicode, falls back neutrally when missing, and recovers to a monogram when an image fails to load.
- Propagate photo URLs through relevant member-bearing DTOs and display the avatar in the member dashboard, member directory, admin directory/detail, and other applicable identity displays.
- Audit the lifecycle and handle upload/database/delete failures without affecting unrelated records.

### Workstream I — Notification-panel close control

`frontend/components/notifications/NotificationBell/index.tsx:37-40` already has a close helper that only changes local open state and optionally restores focus. Escape closes and restores focus; outside pointer clicks close without mutation. Opening the panel only refreshes data. Read mutations occur only through explicit item selection or “Mark all as read.”

The header at `:150-157` has no close control.

**Proposed correction**

- Add the shared `CloseButton` to the panel header.
- Call the existing close helper with focus restoration.
- Do not call `markRead`, `markAllRead`, delete, or any mutation from the close action.
- Add tests asserting that closing preserves `is_read`, `read_at`, unread count, and mutation-call counts.
- Ensure the header remains usable at narrow mobile widths.
- No backend, permission, audit, or migration change is required.

## 6. Root-cause summary

1. **Savings request inconsistency:** a frontend falsy-value branch contradicts an intentional backend allowance for financial members with no current amount.
2. **Repayment notification gap:** submission was implemented as a record-creation endpoint without the notification/audit/idempotency pattern already used by verification and other financial workflows.
3. **Loan lifecycle race:** cancellation/reschedule query and mutate without the row-locking pattern used by decision, disbursement, and verification endpoints.
4. **Terminal-state coupling:** payment review can overwrite a terminal application status, and disabled Cashbook can make a positive-fee verification succeed without its required receipt.
5. **Credential-delivery gap:** password recovery primitives exist, but first-login provisioning still relies on an administrator typing a temporary password into a browser prompt.
6. **Session-policy gap:** the data model and comments anticipate expiry enforcement, but the central authentication dependency implements revocation only.
7. **Profile-photo gap:** the application has storage and validation building blocks but no member-photo domain model or lifecycle.
8. **Notification-close gap:** non-mutating close behavior exists, but the visible control was omitted.
9. **Balance/password visibility gaps:** both are absent UI capabilities, not backend authorization problems.

## 7. Risks and blockers

### High-priority risks

- **Financial duplication:** adding repayment notices without submission idempotency could multiply notices on retries.
- **Receipt completeness:** a positive application fee can be verified while Cashbook is disabled and no receipt is created; the approved policy now requires blocking verification.
- **Cancellation/disbursement race:** a concurrent cancel and approval/disbursement can produce contradictory terminal states.
- **Authentication fail-open behavior:** a valid signed token with a missing or expired session row is currently accepted.
- **Forced-password-change bypass:** frontend redirection does not prevent direct API use by an account that must change its password.
- **Photo privacy:** member photos must not be delivered publicly; authenticated access must be enforced.
- **Migration safety:** new columns/tables must be additive and registered in the ordered migration runner; `create_all()` alone is insufficient.

### Approved decisions — no policy blockers remain

The owner approved the assessment, implementation sequence, and following decisions on 2026-11-27:

1. **Cashbook:** block positive-fee verification whenever Cashbook is disabled, unopened, or period-locked; zero-fee verification remains a no-op. Do not backfill historical receipts automatically.
2. **Repayments:** grant narrowly scoped pending-queue/evidence access to `repayment.verify`; use idempotency only for retries and allow legitimate multiple repayments.
3. **Terminal applications:** allow payment review after cancellation/rejection without changing terminal application status.
4. **First login:** use a token-aware `/change-password`; keep the account `PENDING` until setup succeeds; persist delivery status; newly issued temporary passwords expire after 24 hours; legacy temporary-password accounts require forced reset; use PostgreSQL-backed rate limiting.
5. **Sessions:** meaningful activity is explicit interaction or backend-validated Continue, shared across tabs; eight-hour absolute lifetime; 15-minute admin and 30-minute member idle limits; five-minute warning; unprovable legacy sessions must reauthenticate.
6. **Profile photos:** authenticated-only delivery; JPEG/PNG/WebP; 5 MB input limit; 2048-pixel maximum dimension; admin management requires `member.update` plus conflict-of-interest checks.
7. **Balance visibility:** session-only independent controls for savings, loan, and deduction/contribution balances and derived comparisons; historical transaction amounts remain visible.
8. **Delivery and deployment:** implement and verify locally. No A–I push, merge, deployment, production migration, or production settings change is authorized by this approval.

## 8. Approved implementation sequence

### Phase 0 — Approved baseline

- Refresh this assessment against merged commit `a62320c`.
- Record the completed loan release and the approved decisions above.
- Implement on `feature/mact-controlled-remediation-a-i`; keep `frontend/tsconfig.tsbuildinfo` unstaged.

### Phase 1 — Financial workflows

1. **B:** Fix the Savings request UI and contradictory test; add NULL-amount and failed-history coverage.
2. **A:** Add submission notification, audit, active-account filtering, idempotency, frontend retry key, and narrow verifier queue/evidence access.
3. **G lifecycle:** Add cancellation/reschedule locking, cancellation idempotency, reschedule audit, terminal payment-state handling, historical admin views, and the corrected disbursement count.
4. **G Cashbook:** Enforce the approved disabled/unopened/locked-book block for positive-fee verification; retain the existing posting identity and no historical backfill.

### Phase 2 — Authentication and security

5. **E:** Add the reusable accessible password input and replace all current fields.
6. **C:** Add setup-token purpose/delivery metadata, 30-minute email setup, 24-hour generated temporary passwords, one-time display/Copy, forced-change enforcement, session revocation, and PostgreSQL-backed rate limiting.
7. **F:** Add session activity metadata, role-based idle enforcement, eight-hour absolute expiry, continue-session, polling exclusion, cross-tab coordination, and expiry revocation.

### Phase 3 — Member experience

8. **D:** Add independent session-only balance visibility and apply it consistently to balances and derived comparisons.
9. **H:** Add the authenticated photo schema/API/UI/display lifecycle and reusable avatar fallback.
10. **I:** Add the visible notification-panel close control and non-mutation tests.

### Phase 4 — Integration and regression testing

11. Run targeted tests for every changed workflow.
12. Run the full backend pytest suite against `mact_test`.
13. Run the local smoke test against the sandbox backend only.
14. Run frontend Vitest, TypeScript typecheck, and production build.
15. Verify responsive flows in the browser on an allowed localhost origin.
16. Check migration idempotency locally and review the final diff/generated artifacts.
17. Create the Implementation Report, Test Report, and Changed Files Report.
18. Do not deploy, push, merge, or change production secrets without separate permission.

## 9. Verification status and next gate

**Checks performed for this refreshed baseline**

- Repository identity, branch, commit, and working-tree inspection.
- Static review of current A–I source, models, schemas, routers, services, migrations, permissions, tests, and reports.
- Verification that the loan release is merged, both deployments succeeded, the production migration was applied, and the new columns/constraints/trigger are present.
- Reassessment of the remaining A–I gaps after the loan release.
- No A–I tests, migrations, browser checks, or application-code changes have run in this branch yet.

**Next gate**

Implement Phase 1, then each subsequent phase, with targeted tests before the full local gate. Production rollout remains a separate owner-authorized step.
