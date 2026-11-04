"""
End-to-end smoke test for a running MACT Cooperative Manager backend.

Stage 2 of the offline-testing plan: after code is tested locally and
deployed to a disposable environment (a Vercel Preview wired to a
throwaway Neon branch), this script verifies the DEPLOYED system
actually works end to end -- health, admin login, member lookup, member
login, loan-application submission, read-back -- over real HTTP against
a base URL you pass in.

This is deliberately NOT a replacement for the pytest suite in tests/:
  * pytest exercises business-rule edge cases against a database
    directly; this script exercises the wiring between components
    (auth headers, routing, serialization, DB persistence) against a
    live server.
  * pytest requires a fresh test database; this script requires an
    environment that has already been migrated AND seeded (the local
    sandbox does this via scripts/apply_manual_migrations.py and
    scripts/seed_local_sample_data.py; a Neon branch does via the
    pre-push procedure in LOCAL_TESTING_AND_PRE_PUSH.md).

WARNING: step 7 CREATES a real row -- a pending loan application -- in
whatever database the target server points at. Against a non-localhost
host the script refuses to run unless you pass --yes, as an explicit
acknowledgement that the target is a throwaway environment. Never point
this at production.

Usage (local sandbox -- the defaults match seed_local_sample_data.py):
    backend/.venv/Scripts/python.exe scripts/smoke_test.py \
        --base-url http://127.0.0.1:8000

Usage (remote disposable preview):
    python scripts/smoke_test.py --base-url https://mact-preview.vercel.app \
        --admin-user <preview-admin> --admin-pass <...> \
        --member-user MCT-0001 --member-pass <...> --yes
"""

import argparse
import sys
import uuid
from datetime import datetime, timezone
from urllib.parse import urlparse

import httpx

# 1x1 transparent PNG -- a minimal but genuinely valid image payload so
# the receipt validators (base64 well-formedness, allowed content type)
# are actually exercised rather than bypassed.
TINY_PNG_BASE64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)

LOCAL_HOSTS = {"127.0.0.1", "localhost"}


class SmokeFailure(Exception):
    """A step failed; message says which step and why."""


def api_call(client, method, path, *, token=None, json_body=None, expect=200, label=""):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    try:
        response = client.request(method, path, json=json_body, headers=headers)
    except httpx.HTTPError as exc:
        raise SmokeFailure(f"{label}: request to {path} failed: {exc}")
    if response.status_code != expect:
        body = response.text[:300]
        raise SmokeFailure(
            f"{label}: expected HTTP {expect} from {method} {path}, "
            f"got {response.status_code}: {body}"
        )
    return response.json() if response.content else None


def login(client, username, password, label):
    data = api_call(
        client, "POST", "/api/auth/login",
        json_body={"username": username, "password": password},
        label=label,
    )
    if data.get("must_change_password"):
        raise SmokeFailure(
            f"{label}: account '{username}' still has must_change_password=True. "
            "Use an account whose password was already changed (for the local "
            "sandbox: localadmin and MCT-0001 are ready; MCT-0003 is the "
            "forced-reset test account), or complete the reset flow first."
        )
    return data


def main():
    parser = argparse.ArgumentParser(
        description="End-to-end smoke test against a running backend.",
    )
    parser.add_argument("--base-url", required=True, help="Backend base URL, e.g. http://127.0.0.1:8000")
    parser.add_argument("--admin-user", default="localadmin")
    parser.add_argument("--admin-pass", default="LocalAdmin#2026")
    parser.add_argument("--member-user", default="MCT-0001", help="PSN of the member to test with")
    parser.add_argument("--member-pass", default="MemberTest#2026")
    parser.add_argument("--amount", type=int, default=100000, help="Loan amount for the test application")
    parser.add_argument("--timeout", type=float, default=30.0, help="Per-request timeout in seconds (Vercel cold starts can take a few)")
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Acknowledge that a non-localhost target will receive a real loan application row",
    )
    args = parser.parse_args()

    base_url = args.base_url.rstrip("/")
    host = urlparse(base_url).hostname
    is_local = host in LOCAL_HOSTS
    if not is_local and not args.yes:
        print(
            f"REFUSING TO RUN against {host}: this smoke test CREATES a loan "
            "application row in the target database, so remote targets must be "
            "throwaway environments (a Preview deployment backed by a Neon "
            "branch). If that is what this is, re-run with --yes. Never aim "
            "this at production."
        )
        return 2

    print(f"Target: {base_url}  [{'local sandbox' if is_local else 'REMOTE (--yes given)'}]")
    print(f"Admin:  {args.admin_user}   Member: {args.member_user}\n")

    client = httpx.Client(base_url=base_url, timeout=args.timeout)

    step = 0
    total_steps = 8

    def begin(name):
        nonlocal step
        step += 1
        print(f"[{step}/{total_steps}] {name}")

    try:
        begin("GET /api/health")
        health = api_call(client, "GET", "/api/health", label="health")
        if health.get("status") != "ok":
            raise SmokeFailure(f"health: unexpected payload {health}")
        print("      ok")

        begin(f"Login as admin '{args.admin_user}'")
        admin = login(client, args.admin_user, args.admin_pass, "admin login")
        admin_token = admin["access_token"]
        print(f"      ok (role={admin['role']})")

        begin(f"Member lookup: GET /api/members?search={args.member_user}")
        members = api_call(
            client, "GET", f"/api/members?search={args.member_user}",
            token=admin_token,
            label="member lookup",
        )
        member = next((m for m in members["items"] if m["psn"] == args.member_user), None)
        if not member:
            raise SmokeFailure(
                f"member lookup: PSN {args.member_user!r} not found among "
                f"{members['total']} search matches -- is the target database "
                "seeded? (scripts/seed_local_sample_data.py for the sandbox; "
                "the pre-push procedure seeds branch databases)"
            )
        print(f"      ok (found {member['psn']} -- {member['name']}; total matches={members['total']})")

        begin("GET /api/loan-types")
        loan_types = api_call(client, "GET", "/api/loan-types", token=admin_token, label="loan types")
        loan_type = next((lt for lt in loan_types if lt["is_active"] and lt["open_for_application"]), None)
        if not loan_type:
            raise SmokeFailure(
                "loan types: none of the configured loan types is both active and "
                "open_for_application -- seed data missing or misconfigured"
            )
        print(f"      ok (using '{loan_type['name']}' ({loan_type['id']}), "
              f"rate={loan_type['interest_rate']}, tenure={loan_type['tenure_months']}mo)")

        begin(f"Login as member '{args.member_user}'")
        member_login = login(client, args.member_user, args.member_pass, "member login")
        member_token = member_login["access_token"]
        if member_login["role"] != "member":
            raise SmokeFailure(f"member login: role is {member_login['role']!r}, expected 'member'")
        print("      ok (role=member)")

        begin("GET /api/members/me (member self-record)")
        me = api_call(client, "GET", "/api/members/me", token=member_token, label="member self")
        if me["psn"] != args.member_user:
            raise SmokeFailure(f"member self: PSN mismatch {me['psn']!r} != {args.member_user!r}")
        print(f"      ok ({me['name']} - PSN {me['psn']})")

        begin(f"POST /api/loan-applications (creates a pending application, amount={args.amount})")
        payment_reference = f"SMOKE-{datetime.now(timezone.utc):%Y%m%d%H%M%S}-{uuid.uuid4().hex[:6]}"
        application = api_call(
            client, "POST", "/api/loan-applications",
            token=member_token,
            json_body={
                "loan_type_id": loan_type["id"],
                "requested_amount": args.amount,
                "use_default_account": True,
                "payment_reference": payment_reference,
                "receipt_image_base64": TINY_PNG_BASE64,
                "receipt_content_type": "image/png",
                "member_notes": "smoke test -- safe to ignore/delete",
            },
            expect=201,
            label="submit application",
        )
        if application["member_psn"] != args.member_user:
            raise SmokeFailure(
                f"submit application: response member_psn {application['member_psn']!r} "
                f"!= {args.member_user!r}"
            )
        application_id = application["id"]
        print(f"      ok (id={application_id}, status={application['status']}, "
              f"payment_status={application['payment_status']}, form_fee={application['form_fee_amount']})")

        begin(f"GET /api/loan-applications/{application_id} (read-back)")
        readback = api_call(
            client, "GET", f"/api/loan-applications/{application_id}",
            token=member_token,
            label="application read-back",
        )
        if readback["id"] != application_id:
            raise SmokeFailure(f"read-back: id mismatch {readback['id']} != {application_id}")
        print("      ok")

    except SmokeFailure as exc:
        print(f"\nFAILED at step {step}/{total_steps}: {exc}")
        print("Smoke test FAILED.")
        return 1

    print(f"\nRESULT: {total_steps}/{total_steps} steps passed.")
    print(f"NOTE: a pending loan application was created on {host} "
          f"(payment_reference {payment_reference}, id {application_id}). This is "
          "expected on sandbox/branch databases; it would be real data on production.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
