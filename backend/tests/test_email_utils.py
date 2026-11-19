"""Resend delivery contract, exercised with mocked HTTP.

These tests never touch the network. They lock in the properties the
business code relies on: send_email() reports instead of raising, the
provider response is classified, nothing secret reaches the logs, and a
failed email cannot undo a decision that was already committed.
"""

import logging
from decimal import Decimal

import pytest
import requests

from app import models
from app.cooperative_branding import CooperativeBrand
from app.email_utils import (
    NETWORK_ERROR,
    PROVIDER_ERROR,
    RATE_LIMITED,
    REJECTED,
    SKIPPED,
    SENT,
    TIMEOUT,
    UNAUTHORIZED,
    EmailResult,
    html_to_text,
    loan_rejected_email_html,
    send_email,
)
from tests.conftest import (
    auth_headers,
    grant_permission,
    make_admin_user,
    make_loan_type,
    make_member,
)

API_KEY = "re_test_key_never_log_me"
SENDER = "notifications@mail.example.test"
RECIPIENT = "member@example.test"


class FakeResponse:
    def __init__(self, status_code=200, payload=None, headers=None):
        self.status_code = status_code
        self._payload = payload
        self.headers = headers or {}

    def json(self):
        if self._payload is None:
            raise ValueError("no JSON body")
        return self._payload


@pytest.fixture()
def resend_env(monkeypatch):
    monkeypatch.setenv("RESEND_API_KEY", API_KEY)
    monkeypatch.setenv("FROM_EMAIL", SENDER)


def _capture_post(monkeypatch, response):
    calls = []

    def fake_post(url, **kwargs):
        calls.append((url, kwargs))
        if isinstance(response, Exception):
            raise response
        return response

    monkeypatch.setattr("app.email_utils.requests.post", fake_post)
    return calls


def _forbid_post(monkeypatch):
    def fail(*args, **kwargs):
        raise AssertionError("requests.post must not be called")

    monkeypatch.setattr("app.email_utils.requests.post", fail)


def test_successful_send_returns_message_id(monkeypatch, resend_env):
    calls = _capture_post(monkeypatch, FakeResponse(200, {"id": "msg_123"}))

    result = send_email(
        RECIPIENT, "A subject", "<p>Hello</p>", sender_name="Test Cooperative"
    )

    assert result.ok is True
    assert bool(result) is True
    assert result.status == SENT
    assert result.message_id == "msg_123"

    url, kwargs = calls[0]
    assert url == "https://api.resend.com/emails"
    assert kwargs["headers"]["Authorization"] == f"Bearer {API_KEY}"
    assert kwargs["json"]["from"] == f"Test Cooperative <{SENDER}>"
    assert kwargs["json"]["to"] == [RECIPIENT]
    assert kwargs["json"]["subject"] == "A subject"
    assert kwargs["json"]["html"] == "<p>Hello</p>"
    # A plain-text alternative is always supplied.
    assert kwargs["json"]["text"] == "Hello"
    assert kwargs["timeout"] == (5.0, 10.0)


def test_explicit_sender_display_name_in_env_wins(monkeypatch, resend_env):
    monkeypatch.setenv("FROM_EMAIL", f"Cooperative Desk <{SENDER}>")
    calls = _capture_post(monkeypatch, FakeResponse(200, {"id": "msg_124"}))

    send_email(RECIPIENT, "Subject", "<p>Hello</p>", sender_name="Ignored")

    assert calls[0][1]["json"]["from"] == f"Cooperative Desk <{SENDER}>"


def test_missing_api_key_skips_without_calling_provider(monkeypatch, resend_env):
    monkeypatch.delenv("RESEND_API_KEY")
    _forbid_post(monkeypatch)

    result = send_email(RECIPIENT, "Subject", "<p>Hello</p>")

    assert result.ok is False
    assert result.status == SKIPPED
    assert "RESEND_API_KEY" in result.detail


def test_missing_sender_skips_without_calling_provider(monkeypatch, resend_env):
    monkeypatch.delenv("FROM_EMAIL")
    _forbid_post(monkeypatch)

    result = send_email(RECIPIENT, "Subject", "<p>Hello</p>")

    assert result.status == SKIPPED
    assert "FROM_EMAIL" in result.detail


def test_invalid_sender_skips_without_calling_provider(monkeypatch, resend_env):
    monkeypatch.setenv("FROM_EMAIL", "not an address")
    _forbid_post(monkeypatch)

    result = send_email(RECIPIENT, "Subject", "<p>Hello</p>")

    assert result.status == SKIPPED
    assert "FROM_EMAIL" in result.detail


def test_invalid_recipient_skips_without_calling_provider(monkeypatch, resend_env):
    _forbid_post(monkeypatch)

    result = send_email("not-an-email", "Subject", "<p>Hello</p>")

    assert result.status == SKIPPED
    assert result.detail == "invalid recipient"


def test_http_400_is_classified_as_rejected(monkeypatch, resend_env):
    _capture_post(
        monkeypatch,
        FakeResponse(400, {"name": "validation_error", "message": "sensitive body"}),
    )

    result = send_email(RECIPIENT, "Subject", "<p>Hello</p>")

    assert result.ok is False
    assert result.status == REJECTED
    assert result.retryable is False
    assert "validation_error" in result.detail
    # The provider body is never copied into the result.
    assert "sensitive body" not in result.detail


def test_http_401_is_classified_as_unauthorized(monkeypatch, resend_env):
    _capture_post(monkeypatch, FakeResponse(401, {"name": "invalid_api_key"}))

    result = send_email(RECIPIENT, "Subject", "<p>Hello</p>")

    assert result.status == UNAUTHORIZED
    assert result.retryable is False
    assert API_KEY not in (result.detail or "")


def test_http_429_is_retryable(monkeypatch, resend_env):
    _capture_post(
        monkeypatch,
        FakeResponse(429, {"name": "rate_limit_exceeded"}, headers={"Retry-After": "30"}),
    )

    result = send_email(RECIPIENT, "Subject", "<p>Hello</p>")

    assert result.status == RATE_LIMITED
    assert result.retryable is True


def test_http_500_is_a_retryable_provider_error(monkeypatch, resend_env):
    _capture_post(monkeypatch, FakeResponse(500, {"name": "internal_error"}))

    result = send_email(RECIPIENT, "Subject", "<p>Hello</p>")

    assert result.status == PROVIDER_ERROR
    assert result.retryable is True


def test_connection_failure_is_reported_not_raised(monkeypatch, resend_env):
    _capture_post(monkeypatch, requests.ConnectionError("connection refused"))

    result = send_email(RECIPIENT, "Subject", "<p>Hello</p>")

    assert result.ok is False
    assert result.status == NETWORK_ERROR
    assert result.retryable is True


def test_timeout_is_reported_not_raised(monkeypatch, resend_env):
    _capture_post(monkeypatch, requests.Timeout("timed out"))

    result = send_email(RECIPIENT, "Subject", "<p>Hello</p>")

    assert result.status == TIMEOUT
    assert result.retryable is True


def test_failures_do_not_log_secrets_or_recipients(monkeypatch, resend_env, caplog):
    _capture_post(monkeypatch, FakeResponse(401, {"name": "invalid_api_key"}))

    with caplog.at_level(logging.DEBUG, logger="app.email_utils"):
        result = send_email(RECIPIENT, "Subject", "<p>Hello</p>")

    assert result.status == UNAUTHORIZED
    combined = caplog.text + (result.detail or "")
    assert API_KEY not in combined
    assert RECIPIENT not in combined
    assert "Bearer" not in combined


def test_idempotency_key_is_forwarded(monkeypatch, resend_env):
    calls = _capture_post(monkeypatch, FakeResponse(200, {"id": "msg_125"}))

    send_email(
        RECIPIENT,
        "Subject",
        "<p>Hello</p>",
        idempotency_key="loan-disbursed:abc",
    )

    assert calls[0][1]["headers"]["Idempotency-Key"] == "loan-disbursed:abc"


def test_email_failure_does_not_reverse_a_committed_decision(
    client, db_session, seed_permissions, monkeypatch
):
    reviewer = make_admin_user(db_session, username="email_reject_admin")
    grant_permission(db_session, reviewer, "loan.review", "loan.reject")
    member = make_member(db_session, psn="PSN-EMAIL-1", email=RECIPIENT)
    loan_type = make_loan_type(db_session, "Email Test Loan")

    application = models.LoanApplication(
        member_id=member.id,
        loan_type_id=loan_type.id,
        requested_amount=Decimal("1000"),
        form_fee_amount=Decimal("10"),
        payment_reference="ref-email-1",
        receipt_image_base64="aGVsbG8=",
        receipt_content_type="image/png",
        payment_status=models.PaymentVerificationStatus.VERIFIED,
        status=models.LoanApplicationStatus.PENDING,
    )
    db_session.add(application)
    db_session.commit()
    db_session.refresh(application)

    sent = []

    def failing_send(**kwargs):
        sent.append(kwargs)
        return EmailResult(False, PROVIDER_ERROR, retryable=True)

    monkeypatch.setattr("app.routers.loan_applications.send_email", failing_send)

    response = client.post(
        f"/api/loan-applications/{application.id}/decide",
        json={"approved": False, "admin_notes": "not eligible"},
        headers=auth_headers(reviewer),
    )

    assert response.status_code == 200, response.text
    assert len(sent) == 1
    assert sent[0]["idempotency_key"] == f"loan-rejected:{application.id}"

    db_session.expire_all()
    refreshed = db_session.get(models.LoanApplication, application.id)
    assert refreshed.status == models.LoanApplicationStatus.REJECTED


def test_templates_use_brand_and_escape_interpolated_values():
    brand = CooperativeBrand(name="Test Cooperative", short_name="TC", monogram="T")

    html = loan_rejected_email_html(
        member_name="<b>Bold</b>",
        loan_type_name="Capital Loan",
        requested_amount=1000,
        admin_notes="<script>alert(1)</script>",
        brand=brand,
    )

    assert "Test Cooperative" in html
    assert "<b>Bold</b>" not in html
    assert "&lt;b&gt;Bold&lt;/b&gt;" in html
    assert "<script>" not in html
    assert "Capital Loan" in html

    text = html_to_text(html)
    assert "Test Cooperative" in text
    assert "Capital Loan" in text
    assert "<p>" not in text
