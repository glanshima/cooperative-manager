# MACT Cooperative Manager
## Controlled Remediation Prompt — Members Page Stale Action Error

### PURPOSE

Remediate one specific frontend defect on the **Members** page:

> A self-conflict/action error remains visible after the Members list has successfully reloaded.

Observed behavior:

```text
Admin performs prohibited self-edit
        ↓
Self-conflict error appears
        ↓
Members list reloads successfully
        ↓
"Showing 1–25 of 191 members"
        ↓
OLD error is still displayed
```

This is a stale error-state lifecycle defect.

---

# 1. STRICT SCOPE

This remediation is authorized ONLY to fix the Members-page stale error behavior.

### Allowed

- Inspect the current Members-page frontend implementation.
- Inspect frontend API calls/state handling used by the Members page.
- Modify Members-page frontend error/loading/success state handling as necessary.
- Add or adjust frontend tests if a test framework already exists.
- Perform frontend build/type-check.
- Make the smallest supporting change necessary if inspection proves the issue cannot be fixed correctly without it.

### Explicitly OUT OF SCOPE

Do NOT modify:

- Password Recovery.
- Authentication architecture.
- Admin → Member governance.
- Admin self-link protection.
- Role `requires_member_link`.
- Next-of-Kin.
- `MemberRelationship`.
- `has_member_conflict()`.
- Approval authorization.
- Loan logic.
- Accounting.
- Member search/filter behavior except where necessary to preserve it.
- Backend APIs unless inspection proves the backend is directly responsible for this exact stale-error defect.
- Unrelated UI refactoring.
- Unrelated bug fixes.

If another issue is discovered, report it separately.

---

# 2. INSPECT BEFORE MODIFYING

Do not start by rewriting the page.

First inspect the current Members page and trace the complete lifecycle of:

- list loading;
- list reload;
- mutation/action errors;
- successful mutation;
- successful list reload;
- loading state;
- success state;
- alert rendering;
- request sequencing/race handling.

Identify the exact state variable(s) responsible for the error shown in the screenshot.

Determine whether the current implementation uses separate concepts equivalent to:

```text
listError
actionError
success
```

or whether one shared error state is being reused.

Do not assume the implementation is the same as the Admin Users page.

---

# 3. REPRODUCTION TARGET

Use this exact behavior as the acceptance target.

### Current defect

1. Open Members page.
2. Attempt an administratively prohibited self-edit.
3. Backend returns the self-conflict error.
4. Error is displayed.
5. Members list reloads successfully.
6. The error remains visible.

### Required behavior

1. Open Members page.
2. Attempt the prohibited self-edit.
3. Self-conflict error is displayed.
4. Members list reloads successfully.
5. The stale action error disappears.
6. The refreshed member list remains visible.

The successful reload must not leave the old mutation/action error displayed.

---

# 4. ERROR-STATE MODEL

Separate these concepts where necessary:

### List error

An error preventing the member list from loading/reloading.

### Action error

An error produced by a mutation/action such as editing a member.

### Success

A successful operation message.

Do not allow an old `actionError` to remain visible merely because a subsequent `loadMembers()` succeeds.

Likewise, do not accidentally erase a genuine `listError` while handling an unrelated mutation.

---

# 5. REQUIRED STATE TRANSITIONS

### Initial list load

```text
start list load
    ↓
clear stale list error as appropriate
    ↓
load
    ↓
success → list displayed
```

### Action failure

```text
start action
    ↓
clear previous action error
    ↓
action fails
    ↓
actionError displayed
```

### Successful list reload after action error

```text
actionError exists
        ↓
reload list
        ↓
reload succeeds
        ↓
stale actionError cleared
        ↓
no stale error displayed
```

### List reload failure

```text
reload
  ↓
failure
  ↓
listError displayed
```

Do not incorrectly classify a genuine list-loading failure as an action error.

---

# 6. SUCCESS MUST CLEAR STALE ERROR APPROPRIATELY

A successful operation must not leave an obsolete error message visible.

In particular, when the Members list successfully reloads after a mutation:

```text
actionError → cleared
```

The implementation must not depend on the user manually dismissing an error for normal successful-state cleanup.

A manual Dismiss control may exist if consistent with the existing UI, but it is NOT a substitute for correct state lifecycle management.

---

# 7. RACE / STALE REQUEST SAFETY

Inspect the existing Members-page request sequencing.

Ensure that an older request cannot overwrite newer state.

Example:

```text
Request A ────────────────→ returns late
Request B ─────→ succeeds
```

A stale response from Request A must not resurrect an obsolete error after Request B has successfully refreshed the list.

If the page already has a sequence/request counter, preserve it and extend it only if necessary.

Do not introduce a large state-management framework.

---

# 8. PRESERVE EXISTING MEMBERS FUNCTIONALITY

After remediation, all existing Members functionality must remain intact:

- member list loading;
- pagination;
- search;
- bank filter;
- department filter;
- status filter;
- member editing;
- existing authorization behavior;
- existing self-conflict protection;
- existing backend error messages;
- existing successful operations.

Do not alter the meaning of the self-conflict rule.

The backend remains authoritative.

---

# 9. DO NOT MASK ERRORS

Do NOT fix the issue by simply hiding all errors after reload.

For example, do not implement:

```text
every reload → hide every error
```

if doing so could suppress a genuine current list error.

The goal is correct error ownership and lifecycle, not error suppression.

The UI should show a genuine current error and remove only stale errors.

---

# 10. BACKEND BOUNDARY

Do not modify backend code unless inspection demonstrates that the backend response itself is causing the stale frontend display.

The observed symptom is:

```text
backend action error
        ↓
frontend displays error
        ↓
frontend successfully reloads list
        ↓
frontend still displays old error
```

This strongly suggests a frontend state-lifecycle issue.

Therefore, backend changes require explicit justification in the final report.

If a backend change appears necessary, STOP before making unrelated backend modifications and explain why.

---

# 11. FRONTEND TESTING

Inspect the repository for an existing frontend test framework.

### If one exists

Add a focused regression test for the exact defect:

```text
self-conflict/action error
        ↓
error displayed
        ↓
list reload succeeds
        ↓
error no longer rendered
```

Also test:

1. Action error is displayed after failed action.
2. Successful reload clears stale action error.
3. Genuine list error remains visible when list reload fails.
4. Search/filter behavior is unaffected.
5. A stale/late request cannot resurrect the old error.

### If no frontend test framework exists

Do NOT introduce a new test framework unless explicitly authorized.

Perform:

- TypeScript/type-check;
- production build;
- code-level verification;
- manual/static tracing.

Clearly state that executable frontend tests were unavailable.

---

# 12. BUILD / TYPE CHECK

Run the project's existing frontend validation commands.

Report separately:

```text
Type-check: PASS / FAIL / NOT RUN
Production build: PASS / FAIL / NOT RUN
Frontend tests: PASS / FAIL / NOT RUN
```

Do not claim a test passed if it was only inspected.

---

# 13. VISUAL / BEHAVIORAL ACCEPTANCE TEST

The supplied screenshot represents the defect.

The final implementation must make this state impossible after a successful reload:

```text
Error: You cannot administratively edit your own member record...
```

remaining above:

```text
Showing 1–25 of 191 members
```

when the list reload itself has succeeded.

Expected final state:

```text
Members

Search...
Filters...

Showing 1–25 of 191 members
```

with **no stale previous action error**.

A current, genuine error may still be displayed when appropriate.

---

# 14. REGRESSION CHECK

Verify that the fix does not break:

- Members page loading;
- search;
- filters;
- pagination;
- edit flow;
- self-conflict enforcement;
- backend error handling;
- successful edits;
- list refresh.

Also confirm that no files related to:

- Password Recovery;
- Admin → Member governance;
- Next-of-Kin;
- roles;
- authentication

were unnecessarily modified.

---

# 15. STOP CONDITIONS

STOP and report instead of expanding scope if:

1. The defect cannot be fixed safely within the Members frontend.
2. Backend modification appears necessary.
3. Fixing the issue would require changing authorization rules.
4. Fixing the issue would affect Admin → Member governance.
5. Fixing the issue would affect Next-of-Kin or MemberRelationship.
6. Fixing the issue requires broad frontend refactoring.
7. The current repository differs materially from the implementation being described.
8. A regression is discovered in unrelated functionality.

Do not silently expand scope.

---

# 16. DEFINITION OF DONE

The remediation is complete only when:

- The exact stale-error scenario is traced.
- The root cause is identified.
- The smallest appropriate frontend fix is implemented.
- A successful Members list reload clears the stale action/self-conflict error.
- Genuine list errors remain visible.
- Stale requests cannot resurrect obsolete errors where applicable.
- Existing Members functionality remains intact.
- Type-check/build is completed where available.
- Regression testing is performed where available.
- No unrelated security/governance functionality is modified.
- The final report clearly distinguishes executed tests from static inspection.

---

# 17. FINAL REPORT FORMAT

Return:

## A. Root cause

Explain exactly why the stale self-conflict error remained visible after a successful list reload.

## B. Fix implemented

Describe the exact state/lifecycle change.

## C. Reproduction

Confirm whether the original sequence was reproduced or statically traced.

## D. Acceptance behavior

Confirm:

```text
Action error
    ↓
List reload succeeds
    ↓
Stale error disappears
```

## E. Race/stale request handling

Describe what protects against old requests overwriting newer state.

## F. Files changed

List every changed file.

## G. Backend changes

State explicitly:

- No backend files changed; OR
- Backend files changed, with exact justification.

## H. Tests

For each test state:

- PASS — executed;
- FAIL — executed and failed;
- NOT RUN — reason.

Never label static inspection as an executed test.

## I. Build/type-check

Report actual results.

## J. Regression verification

Separate:

- executed verification;
- static/code-level verification;
- unavailable verification.

## K. Remaining gaps

List only genuine remaining issues.

---

# AUTHORIZATION BOUNDARY

This prompt authorizes ONLY the remediation of the **Members-page stale action/self-conflict error lifecycle**.

The implementation must preserve the existing MACT architecture and all existing governance rules.

**Do not redesign. Do not broaden scope. Inspect first, fix the root cause, verify the exact screenshot scenario, and report honestly.**
