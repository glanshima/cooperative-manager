"""
Shared server-side input validation helpers (Phase 1, Section 21).
Applied via pydantic field_validator in schemas.py.

These are deliberately conservative/format-level checks (not business
rules) -- e.g. "is this syntactically an email address", not "does this
email domain match the cooperative's employer". Business-rule validation
belongs in the router layer, close to the data it needs to check against.
"""
import base64
import re
from decimal import Decimal
from typing import Optional

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
# Digits, spaces, +, -, () -- covers most phone formats without being a
# strict E.164 validator (the source spreadsheet data predates any such
# constraint, so this Phase 1 pass validates format sanity, not a rewrite
# of existing phone data).
PHONE_RE = re.compile(r"^[0-9+\-() ]{6,20}$")

MAX_RECEIPT_BASE64_CHARS = 7_000_000  # ~5MB decoded, generous for a phone photo
ALLOWED_RECEIPT_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp", "image/heic", "application/pdf"}


def validate_email_format(value: Optional[str]) -> Optional[str]:
    if value is None or value == "":
        return value
    value = value.strip()
    if not EMAIL_RE.match(value):
        raise ValueError("Not a valid email address")
    return value


def validate_phone_format(value: Optional[str]) -> Optional[str]:
    if value is None or value == "":
        return value
    value = value.strip()
    if not PHONE_RE.match(value):
        raise ValueError("Not a valid phone number")
    return value


def validate_psn(value: str) -> str:
    value = value.strip()
    if not value:
        raise ValueError("PSN cannot be blank")
    if len(value) > 64:
        raise ValueError("PSN is too long")
    # Reject characters that have no business in an identifier and are
    # common path-traversal / injection probes.
    if re.search(r"[\/\\'\";<>]", value):
        raise ValueError("PSN contains invalid characters")
    return value


def validate_positive_amount(value: Decimal) -> Decimal:
    if value is None or value <= 0:
        raise ValueError("Amount must be greater than zero")
    return value


def validate_positive_amount_optional(value: Optional[Decimal]) -> Optional[Decimal]:
    if value is None:
        return value
    return validate_positive_amount(value)


def validate_receipt_content_type(value: str) -> str:
    if value not in ALLOWED_RECEIPT_CONTENT_TYPES:
        raise ValueError(
            f"Unsupported receipt file type {value!r}. Allowed: {', '.join(sorted(ALLOWED_RECEIPT_CONTENT_TYPES))}"
        )
    return value


def validate_receipt_base64(value: str) -> str:
    if len(value) > MAX_RECEIPT_BASE64_CHARS:
        raise ValueError("Receipt file is too large")
    try:
        # validate=True rejects non-alphabet characters, catching
        # malformed/non-base64 payloads (and, incidentally, most attempts
        # to smuggle something other than an actual image/PDF through
        # this field) before it's ever stored.
        base64.b64decode(value, validate=True)
    except Exception:
        raise ValueError("Receipt file is not valid base64-encoded data")
    return value
