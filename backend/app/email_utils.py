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
) -> str:
    account_lines = ""
    if disbursement_bank_name:
        account_lines += f"<tr><td style='padding: 4px 8px;'>Bank</td><td style='padding: 4px 8px;'>{disbursement_bank_name}</td></tr>"
    if disbursement_account_name:
        account_lines += f"<tr><td style='padding: 4px 8px;'>Account name</td><td style='padding: 4px 8px;'>{disbursement_account_name}</td></tr>"
    if disbursement_account_number:
        account_lines += f"<tr><td style='padding: 4px 8px;'>Account number</td><td style='padding: 4px 8px;'>{disbursement_account_number}</td></tr>"

    deduction_line = (
        f"<tr><td style='padding: 4px 8px;'>Deducted for existing loan(s)</td>"
        f"<td style='padding: 4px 8px;'>-{deducted_amount}</td></tr>"
        if deducted_amount
        else ""
    )
    return f"""
    <div style="font-family: sans-serif; max-width: 600px;">
      <h2>Your loan has been disbursed</h2>
      <p>Dear {member_name},</p>
      <p>Your <strong>{loan_type_name}</strong> has been disbursed. Details below:</p>
      <table style="border-collapse: collapse; width: 100%;">
        <tr><td style="padding: 4px 8px;">Approved amount</td><td style="padding: 4px 8px;"><strong>{approved_amount}</strong></td></tr>
        <tr><td style="padding: 4px 8px;">Interest (deducted at source)</td><td style="padding: 4px 8px;">{interest_amount}</td></tr>
        {deduction_line}
        <tr><td style="padding: 4px 8px;">Amount you will receive</td><td style="padding: 4px 8px;"><strong>{net_disbursed}</strong></td></tr>
        <tr><td style="padding: 4px 8px;">Total repayable</td><td style="padding: 4px 8px;">{total_repayable}</td></tr>
        <tr><td style="padding: 4px 8px;">Monthly installment</td><td style="padding: 4px 8px;">{monthly_installment}</td></tr>
        <tr><td style="padding: 4px 8px;">Repayment period</td><td style="padding: 4px 8px;">{tenure_months} months</td></tr>
        <tr><td style="padding: 4px 8px;">Disbursement date</td><td style="padding: 4px 8px;">{disbursement_date}</td></tr>
        <tr><td style="padding: 4px 8px;">Expected completion</td><td style="padding: 4px 8px;">{expected_end_date}</td></tr>
        {account_lines}
      </table>
      <p>You can view these details and service your loan any time from your dashboard.</p>
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


def repayment_verified_email_html(member_name: str, loan_type_name: str, amount, new_balance) -> str:
    return f"""
    <div style="font-family: sans-serif; max-width: 600px;">
      <h2>Repayment received</h2>
      <p>Dear {member_name},</p>
      <p>We've verified your repayment of <strong>{amount}</strong> toward your <strong>{loan_type_name}</strong>.</p>
      <p>Your remaining balance is now <strong>{new_balance}</strong>.</p>
    </div>
    """


def repayment_rejected_email_html(member_name: str, loan_type_name: str, reason: str = "") -> str:
    reason_block = f"<p><strong>Reason:</strong> {reason}</p>" if reason else ""
    return f"""
    <div style="font-family: sans-serif; max-width: 600px;">
      <h2>Your repayment could not be verified</h2>
      <p>Dear {member_name},</p>
      <p>We were unable to verify a repayment receipt you submitted for your <strong>{loan_type_name}</strong>.</p>
      {reason_block}
      <p>Please submit the receipt again with a valid reference.</p>
    </div>
    """


def password_reset_email_html(recipient_name: str, reset_url: str, expires_minutes: int = 15) -> str:
    return f"""
    <div style="font-family: sans-serif; max-width: 600px; line-height: 1.5; color: #333;">
      <h2>Password Reset Request</h2>
      <p>Dear {recipient_name},</p>
      <p>We received a request to reset your MACT Cooperative Manager password. Click the button below to set a new password:</p>
      <p style="margin: 24px 0;">
        <a href="{reset_url}" style="background-color: #0066cc; color: #ffffff; padding: 12px 24px; text-decoration: none; border-radius: 4px; display: inline-block; font-weight: bold;">
          Reset Password
        </a>
      </p>
      <p style="color: #666; font-size: 14px;">
        Or copy and paste this link into your browser:<br/>
        <a href="{reset_url}" style="color: #0066cc;">{reset_url}</a>
      </p>
      <p style="color: #666; font-size: 14px;">
        This link is single-use and will expire in <strong>{expires_minutes} minutes</strong>.
      </p>
      <hr style="border: none; border-top: 1px solid #eee; margin: 24px 0;" />
      <p style="color: #999; font-size: 12px;">
        If you did not request a password reset, you can safely ignore this email or notify the cooperative administrator. Your password will remain unchanged.
      </p>
    </div>
    """
