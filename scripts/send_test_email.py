"""Send one real test email through the configured Resend account.

This is the delivery gate: a successful API response is not proof of
delivery, so after running this, open the destination inbox (and its junk
folder) and confirm the message arrived.

Usage (from the repository root):
    backend/.venv/Scripts/python.exe scripts/send_test_email.py you@example.com

Reads RESEND_API_KEY and FROM_EMAIL from backend/.env; values already in
the process environment win over the file. The recipient must be an
address you own or are explicitly allowed to mail -- this sends a real
message. The cooperative identity shown is the deployment default, not
the Settings row.

Never prints the API key. Exit code 0 means Resend accepted the message;
1 means it did not (the reason is printed); 2 means bad usage.
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))

import dotenv  # noqa: E402

dotenv.load_dotenv(os.path.join(ROOT, "backend", ".env"), override=False)

from app.cooperative_branding import DEFAULT_BRAND  # noqa: E402
from app.email_utils import send_email  # noqa: E402

HTML = """
<div style="font-family: Arial, Helvetica, sans-serif; max-width: 600px; line-height: 1.55; color: #102a4c;">
  <h1 style="font-size: 22px; color: #082b59;">Resend delivery test</h1>
  <p>This message was sent by <code>scripts/send_test_email.py</code> to confirm that
  transactional email is configured for this deployment.</p>
  <p>If you can read it, delivery works. No action is needed.</p>
</div>
"""


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python scripts/send_test_email.py <recipient@example.com>")
        return 2

    result = send_email(
        to=sys.argv[1],
        subject=f"Test email from {DEFAULT_BRAND.name}",
        html=HTML,
        sender_name=DEFAULT_BRAND.name,
    )

    if result.ok:
        print(f"Resend accepted the message (message id: {result.message_id or 'not returned'}).")
        print("Now confirm receipt in the destination inbox, including the junk folder.")
        return 0

    print(f"Not sent: {result.status}" + (f" -- {result.detail}" if result.detail else ""))
    if result.status == "skipped":
        print("Set RESEND_API_KEY and FROM_EMAIL in backend/.env, then rerun.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
