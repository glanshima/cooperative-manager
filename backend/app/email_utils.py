"""
Minimal Resend integration -- a plain HTTP POST, no SDK dependency needed
for our one use case (sending a single templated email on loan decisions).

Requires these environment variables:
    RESEND_API_KEY  - from your Resend dashboard
    FROM_EMAIL      - a verified sender address on your Resend domain,
                      e.g. "MACT Cooperative <loans@yourdomain.com>"

If either is missing, send_email() logs a warning and returns False
instead of raising -- a missing email config shouldn't crash a loan
approval that otherwise succeeded in the database.
"""

import os
import logging

import requests

logger = logging.getLogger(__name__)

RESEND_API_KEY = os.getenv("RESEND_API_KEY")
FROM_EMAIL = os.getenv("FROM_EMAIL")
RESEND_API_URL = "https://api.resend.com/emails"


def send_email(to: str, subject: str, html: str) -> bool:
    if not RESEND_API_KEY or not FROM_EMAIL:
        logger.warning(
            "RESEND_API_KEY or FROM_EMAIL not set -- skipping email send to %s", to
        )
        return False

    if not to:
        logger.warning("No recipient email address -- skipping email send")
        return False

    try:
        response = requests.post(
            RESEND_API_URL,
            headers={"Authorization": f"Bearer {RESEND_API_KEY}"},
            json={"from": FROM_EMAIL, "to": [to], "subject": subject, "html": html},
            timeout=10,
        )
        response.raise_for_status()
        return True
    except requests.RequestException as e:
        logger.error("Failed to send email to %s: %s", to, e)
        return False


def loan_approved_email_html(
    member_name: str,
    loan_type_name: str,
    requested_amount,
    approved_amount,
    interest_amount,
    total_repayable,
    monthly_installment,
    tenure_months: int,
    disbursement_date,
    expected_end_date,
    admin_notes: str = "",
) -> str:
    notes_block = f"<p><strong>Note from the cooperative:</strong> {admin_notes}</p>" if admin_notes else ""
    return f"""
    <div style="font-family: sans-serif; max-width: 600px;">
      <h2>Your loan application has been approved</h2>
      <p>Dear {member_name},</p>
      <p>Your application for a <strong>{loan_type_name}</strong> has been approved. Details below:</p>
      <table style="border-collapse: collapse; width: 100%;">
        <tr><td style="padding: 4px 8px;">Amount requested</td><td style="padding: 4px 8px;">{requested_amount}</td></tr>
        <tr><td style="padding: 4px 8px;">Amount approved</td><td style="padding: 4px 8px;"><strong>{approved_amount}</strong></td></tr>
        <tr><td style="padding: 4px 8px;">Interest</td><td style="padding: 4px 8px;">{interest_amount}</td></tr>
        <tr><td style="padding: 4px 8px;">Total repayable</td><td style="padding: 4px 8px;">{total_repayable}</td></tr>
        <tr><td style="padding: 4px 8px;">Monthly installment</td><td style="padding: 4px 8px;">{monthly_installment}</td></tr>
        <tr><td style="padding: 4px 8px;">Repayment period</td><td style="padding: 4px 8px;">{tenure_months} months</td></tr>
        <tr><td style="padding: 4px 8px;">Disbursement date</td><td style="padding: 4px 8px;">{disbursement_date}</td></tr>
        <tr><td style="padding: 4px 8px;">Expected completion</td><td style="padding: 4px 8px;">{expected_end_date}</td></tr>
      </table>
      {notes_block}
      <p>You can view these details any time from your dashboard.</p>
    </div>
    """


def loan_rejected_email_html(member_name: str, loan_type_name: str, requested_amount, admin_notes: str = "") -> str:
    notes_block = f"<p><strong>Reason:</strong> {admin_notes}</p>" if admin_notes else ""
    return f"""
    <div style="font-family: sans-serif; max-width: 600px;">
      <h2>Update on your loan application</h2>
      <p>Dear {member_name},</p>
      <p>Your application for a <strong>{loan_type_name}</strong> ({requested_amount}) was not approved at this time.</p>
      {notes_block}
      <p>You're welcome to discuss this with the cooperative office or apply again in future.</p>
    </div>
    """


def payment_rejected_email_html(member_name: str, loan_type_name: str, reason: str = "") -> str:
    reason_block = f"<p><strong>Reason:</strong> {reason}</p>" if reason else ""
    return f"""
    <div style="font-family: sans-serif; max-width: 600px;">
      <h2>Your loan form payment could not be verified</h2>
      <p>Dear {member_name},</p>
      <p>We were unable to verify the payment receipt submitted for your <strong>{loan_type_name}</strong> application.</p>
      {reason_block}
      <p>Please submit a new application with a valid payment reference and receipt.</p>
    </div>
    """
