"""
Transactional email delivery through Resend.

A plain HTTPS POST -- no SDK. Configuration is read from the environment
at call time (not import time) so tests and scripts can set it without
re-importing the module:

    RESEND_API_KEY  API key from https://resend.com/api-keys. Backend only;
                    never expose it to the browser or commit it.
    FROM_EMAIL      Verified sender. Either "address@domain" (the brand
                    name is then used as the display name) or an explicit
                    "Display Name <address@domain>".

send_email() never raises. It returns an EmailResult whose `ok` flag is
safe to ignore: a failed or skipped send is logged and must never change
the outcome of the business operation that triggered it. Callers that
care can log the result's status, which contains no recipient, subject
or credential.

No automatic retries are performed -- a retry loop around a non-idempotent
provider call risks duplicate mail. Pass `idempotency_key` when the same
logical message may be attempted more than once; Resend de-duplicates on
that key for 24 hours.
"""

from __future__ import annotations

import html as html_module
import logging
import os
import re
from dataclasses import dataclass

import requests

from .cooperative_branding import DEFAULT_BRAND, CooperativeBrand

logger = logging.getLogger(__name__)

RESEND_API_URL = "https://api.resend.com/emails"
CONNECT_TIMEOUT_SECONDS = 5.0
READ_TIMEOUT_SECONDS = 10.0

# Deliberately loose: the provider is the final authority. This only
# catches values that could never be an address (empty, no @, no dot).
_EMAIL_ADDRESS_RE = re.compile(r"^[^@\s<>]+@[^@\s<>]+\.[^@\s<>]+$")
_BLOCK_BREAK_RE = re.compile(r"(?i)<br\s*/?>|</(?:p|div|tr|h[1-6]|li)>")
_TAG_RE = re.compile(r"<[^>]+>")
_INLINE_SPACE_RE = re.compile(r"[ \t]+")
_EXCESS_NEWLINES_RE = re.compile(r"\n{3,}")

# Result statuses. "sent" is the only success; the others say why not.
SENT = "sent"
SKIPPED = "skipped"
REJECTED = "rejected"
UNAUTHORIZED = "unauthorized"
RATE_LIMITED = "rate_limited"
PROVIDER_ERROR = "provider_error"
NETWORK_ERROR = "network_error"
TIMEOUT = "timeout"


@dataclass(frozen=True)
class EmailResult:
    ok: bool
    status: str
    message_id: str | None = None
    retryable: bool = False
    # Safe diagnostic only -- never the API key, recipient or provider body.
    detail: str | None = None

    def __bool__(self) -> bool:
        return self.ok


def send_email(
    to: str,
    subject: str,
    html: str,
    *,
    text: str | None = None,
    reply_to: str | None = None,
    idempotency_key: str | None = None,
    sender_name: str | None = None,
) -> EmailResult:
    recipient = (to or "").strip()
    if not recipient:
        logger.warning("Email skipped: no recipient address")
        return EmailResult(False, SKIPPED, detail="missing recipient")
    if not _EMAIL_ADDRESS_RE.match(recipient):
        logger.warning("Email skipped: recipient address is not valid")
        return EmailResult(False, SKIPPED, detail="invalid recipient")

    api_key = (os.getenv("RESEND_API_KEY") or "").strip()
    from_email = (os.getenv("FROM_EMAIL") or "").strip()
    sender = _sender_address(from_email, sender_name)

    missing = []
    if not api_key:
        missing.append("RESEND_API_KEY")
    if not sender:
        missing.append("FROM_EMAIL")
    if missing:
        logger.warning(
            "Email skipped: missing or invalid configuration (%s)", ", ".join(missing)
        )
        return EmailResult(
            False, SKIPPED, detail=f"configuration missing: {', '.join(missing)}"
        )

    payload = {
        "from": sender,
        "to": [recipient],
        "subject": subject,
        "html": html,
        "text": text if text is not None else html_to_text(html),
    }
    if reply_to:
        payload["reply_to"] = reply_to

    headers = {"Authorization": f"Bearer {api_key}"}
    if idempotency_key:
        headers["Idempotency-Key"] = idempotency_key

    try:
        response = requests.post(
            RESEND_API_URL,
            headers=headers,
            json=payload,
            timeout=(CONNECT_TIMEOUT_SECONDS, READ_TIMEOUT_SECONDS),
        )
    except requests.Timeout:
        logger.warning("Email delivery timed out")
        return EmailResult(False, TIMEOUT, retryable=True)
    except requests.RequestException:
        logger.warning("Email delivery failed: network error")
        return EmailResult(False, NETWORK_ERROR, retryable=True)

    if response.status_code in (200, 201, 202):
        message_id = _response_message_id(response)
        logger.info("Email accepted by Resend (message_id=%s)", message_id)
        return EmailResult(True, SENT, message_id=message_id)

    if response.status_code in (401, 403):
        logger.error(
            "Email delivery failed: Resend rejected the API credentials (HTTP %s)",
            response.status_code,
        )
        return EmailResult(
            False, UNAUTHORIZED, detail=f"HTTP {response.status_code}"
        )

    if response.status_code == 429:
        retry_after = response.headers.get("Retry-After")
        logger.warning(
            "Email delivery rate limited by Resend (retry after %s)",
            retry_after or "an unspecified delay",
        )
        return EmailResult(False, RATE_LIMITED, retryable=True, detail="HTTP 429")

    if response.status_code >= 500:
        logger.error(
            "Email delivery failed: Resend server error (HTTP %s)",
            response.status_code,
        )
        return EmailResult(
            False, PROVIDER_ERROR, retryable=True, detail=f"HTTP {response.status_code}"
        )

    code = _response_error_code(response)
    logger.warning(
        "Email rejected by Resend (HTTP %s%s)",
        response.status_code,
        f", code={code}" if code else "",
    )
    detail = f"HTTP {response.status_code}"
    return EmailResult(False, REJECTED, detail=f"{detail} {code}" if code else detail)


def _sender_address(from_email: str, display_name: str | None) -> str | None:
    """Returns a usable From header, or None when FROM_EMAIL is missing or
    cannot be an address. An explicit "Name <addr>" in the env value wins
    over the brand-derived display name."""
    value = from_email.strip()
    if not value:
        return None
    if "<" in value and ">" in value:
        return value
    if not _EMAIL_ADDRESS_RE.match(value):
        return None
    return f"{display_name} <{value}>" if display_name else value


def _response_message_id(response) -> str | None:
    try:
        data = response.json()
    except ValueError:
        return None
    if isinstance(data, dict) and isinstance(data.get("id"), str):
        return data["id"]
    return None


def _response_error_code(response) -> str | None:
    """The provider's short machine-readable error name, if it sent one.
    Bounded and charset-checked so no provider body can reach the logs."""
    try:
        data = response.json()
    except ValueError:
        return None
    name = data.get("name") if isinstance(data, dict) else None
    if isinstance(name, str) and re.fullmatch(r"[A-Za-z0-9_.-]{1,64}", name):
        return name
    return None


def html_to_text(html: str) -> str:
    """A plain-text alternative for the simple templates below. Anchors
    degrade to their text; these templates always repeat the URL."""
    text = _BLOCK_BREAK_RE.sub("\n", html)
    text = _TAG_RE.sub("", text)
    text = html_module.unescape(text)
    text = _INLINE_SPACE_RE.sub(" ", text)
    lines = [line.strip() for line in text.splitlines()]
    return _EXCESS_NEWLINES_RE.sub("\n\n", "\n".join(lines)).strip()


def _layout(title: str, body: str, brand: CooperativeBrand) -> str:
    name = html_module.escape(brand.name)
    return f"""<!doctype html>
    <html>
      <body style="margin: 0; padding: 24px; background-color: #f4f6f8;">
        <div style="font-family: Arial, Helvetica, sans-serif; max-width: 600px; margin: 0 auto; background-color: #ffffff; border-radius: 8px; padding: 32px; color: #102a4c; line-height: 1.55;">
          <p style="margin: 0 0 24px; font-size: 13px; font-weight: 700; letter-spacing: 0.08em; text-transform: uppercase; color: #0876c9;">{name}</p>
          <h1 style="margin: 0 0 16px; font-size: 22px; color: #082b59;">{html_module.escape(title)}</h1>
          {body}
        </div>
        <p style="max-width: 600px; margin: 16px auto 0; font-family: Arial, Helvetica, sans-serif; font-size: 12px; color: #60748c; text-align: center;">
          This is an automated message from {name}.
        </p>
      </body>
    </html>"""


def loan_disbursed_email_html(
    member_name: str,
    loan_type_name: str,
    approved_amount,
    interest_amount,
    net_disbursed,
    total_repayable,
    monthly_installment,
    tenure_months: int,
    disbursement_date,
    expected_end_date,
    disbursement_bank_name: str = "",
    disbursement_account_name: str = "",
    disbursement_account_number: str = "",
    deducted_amount=None,
    *,
    brand: CooperativeBrand = DEFAULT_BRAND,
) -> str:
    account_lines = ""
    if disbursement_bank_name:
        account_lines += f"<tr><td style='padding: 4px 8px;'>Bank</td><td style='padding: 4px 8px;'>{html_module.escape(disbursement_bank_name)}</td></tr>"
    if disbursement_account_name:
        account_lines += f"<tr><td style='padding: 4px 8px;'>Account name</td><td style='padding: 4px 8px;'>{html_module.escape(disbursement_account_name)}</td></tr>"
    if disbursement_account_number:
        account_lines += f"<tr><td style='padding: 4px 8px;'>Account number</td><td style='padding: 4px 8px;'>{html_module.escape(disbursement_account_number)}</td></tr>"

    deduction_line = (
        f"<tr><td style='padding: 4px 8px;'>Deducted for existing loan(s)</td>"
        f"<td style='padding: 4px 8px;'>-{html_module.escape(str(deducted_amount))}</td></tr>"
        if deducted_amount
        else ""
    )
    body = f"""
      <p>Dear {html_module.escape(member_name)},</p>
      <p>Your <strong>{html_module.escape(loan_type_name)}</strong> has been disbursed. Details below:</p>
      <table style="border-collapse: collapse; width: 100%;">
        <tr><td style="padding: 4px 8px;">Approved amount</td><td style="padding: 4px 8px;"><strong>{html_module.escape(str(approved_amount))}</strong></td></tr>
        <tr><td style="padding: 4px 8px;">Interest (deducted at source)</td><td style="padding: 4px 8px;">{html_module.escape(str(interest_amount))}</td></tr>
        {deduction_line}
        <tr><td style="padding: 4px 8px;">Amount you will receive</td><td style="padding: 4px 8px;"><strong>{html_module.escape(str(net_disbursed))}</strong></td></tr>
        <tr><td style="padding: 4px 8px;">Total repayable</td><td style="padding: 4px 8px;">{html_module.escape(str(total_repayable))}</td></tr>
        <tr><td style="padding: 4px 8px;">Monthly installment</td><td style="padding: 4px 8px;">{html_module.escape(str(monthly_installment))}</td></tr>
        <tr><td style="padding: 4px 8px;">Repayment period</td><td style="padding: 4px 8px;">{int(tenure_months)} months</td></tr>
        <tr><td style="padding: 4px 8px;">Disbursement date</td><td style="padding: 4px 8px;">{html_module.escape(str(disbursement_date))}</td></tr>
        <tr><td style="padding: 4px 8px;">Expected completion</td><td style="padding: 4px 8px;">{html_module.escape(str(expected_end_date))}</td></tr>
        {account_lines}
      </table>
      <p>You can view these details and service your loan any time from your dashboard.</p>
    """
    return _layout("Your loan has been disbursed", body, brand)


def loan_rejected_email_html(
    member_name: str,
    loan_type_name: str,
    requested_amount,
    admin_notes: str = "",
    *,
    brand: CooperativeBrand = DEFAULT_BRAND,
) -> str:
    notes_block = (
        f"<p><strong>Reason:</strong> {html_module.escape(admin_notes)}</p>"
        if admin_notes
        else ""
    )
    body = f"""
      <p>Dear {html_module.escape(member_name)},</p>
      <p>Your application for a <strong>{html_module.escape(loan_type_name)}</strong> ({html_module.escape(str(requested_amount))}) was not approved at this time.</p>
      {notes_block}
      <p>You're welcome to discuss this with the cooperative office or apply again in future.</p>
    """
    return _layout("Update on your loan application", body, brand)


def payment_rejected_email_html(
    member_name: str,
    loan_type_name: str,
    reason: str = "",
    *,
    brand: CooperativeBrand = DEFAULT_BRAND,
) -> str:
    reason_block = (
        f"<p><strong>Reason:</strong> {html_module.escape(reason)}</p>" if reason else ""
    )
    body = f"""
      <p>Dear {html_module.escape(member_name)},</p>
      <p>We were unable to verify the payment receipt submitted for your <strong>{html_module.escape(loan_type_name)}</strong> application.</p>
      {reason_block}
      <p>Please submit a new application with a valid payment reference and receipt.</p>
    """
    return _layout("Your loan form payment could not be verified", body, brand)


def repayment_verified_email_html(
    member_name: str,
    loan_type_name: str,
    amount,
    new_balance,
    *,
    brand: CooperativeBrand = DEFAULT_BRAND,
) -> str:
    body = f"""
      <p>Dear {html_module.escape(member_name)},</p>
      <p>We've verified your repayment of <strong>{html_module.escape(str(amount))}</strong> toward your <strong>{html_module.escape(loan_type_name)}</strong>.</p>
      <p>Your remaining balance is now <strong>{html_module.escape(str(new_balance))}</strong>.</p>
    """
    return _layout("Repayment received", body, brand)


def repayment_rejected_email_html(
    member_name: str,
    loan_type_name: str,
    reason: str = "",
    *,
    brand: CooperativeBrand = DEFAULT_BRAND,
) -> str:
    reason_block = (
        f"<p><strong>Reason:</strong> {html_module.escape(reason)}</p>" if reason else ""
    )
    body = f"""
      <p>Dear {html_module.escape(member_name)},</p>
      <p>We were unable to verify a repayment receipt you submitted for your <strong>{html_module.escape(loan_type_name)}</strong>.</p>
      {reason_block}
      <p>Please submit the receipt again with a valid reference.</p>
    """
    return _layout("Your repayment could not be verified", body, brand)


def password_reset_email_html(
    recipient_name: str,
    reset_url: str,
    expires_minutes: int = 15,
    *,
    brand: CooperativeBrand = DEFAULT_BRAND,
) -> str:
    safe_url = html_module.escape(reset_url, quote=True)
    body = f"""
      <p>Dear {html_module.escape(recipient_name)},</p>
      <p>We received a request to reset your {html_module.escape(brand.name)} password. Click the button below to set a new password:</p>
      <p style="margin: 24px 0;">
        <a href="{safe_url}" style="background-color: #0876c9; color: #ffffff; padding: 12px 24px; text-decoration: none; border-radius: 6px; display: inline-block; font-weight: bold;">
          Reset Password
        </a>
      </p>
      <p style="color: #60748c; font-size: 14px;">
        Or copy and paste this link into your browser:<br/>
        <a href="{safe_url}" style="color: #0876c9;">{safe_url}</a>
      </p>
      <p style="color: #60748c; font-size: 14px;">
        This link is single-use and will expire in <strong>{int(expires_minutes)} minutes</strong>.
      </p>
      <hr style="border: none; border-top: 1px solid #e6ebf1; margin: 24px 0;" />
      <p style="color: #8a9aad; font-size: 12px;">
        If you did not request a password reset, you can safely ignore this email or notify the cooperative administrator. Your password will remain unchanged.
      </p>
    """
    return _layout("Password reset request", body, brand)
