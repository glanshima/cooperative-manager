"""
Shared server-side input validation helpers (Phase 1, Section 21).
Applied via pydantic field_validator in schemas.py.

These are deliberately conservative/format-level checks (not business
rules) -- e.g. "is this syntactically an email address", not "does this
email domain match the cooperative's employer". Business-rule validation
belongs in the router layer, close to the data it needs to check against.
"""
import base64
import binascii
import re
from datetime import date
from decimal import Decimal
from typing import Optional

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MONTH_RE = re.compile(r"^(\d{4})-(0[1-9]|1[0-2])$")
# Digits, spaces, +, -, () -- covers most phone formats without being a
# strict E.164 validator (the source spreadsheet data predates any such
# constraint, so this Phase 1 pass validates format sanity, not a rewrite
# of existing phone data).
PHONE_RE = re.compile(r"^[0-9+\-() ]{6,20}$")

MAX_RECEIPT_BASE64_CHARS = 7_000_000  # ~5MB decoded, generous for a phone photo
ALLOWED_RECEIPT_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp", "image/heic", "application/pdf"}

# Cooperative logo uploads. Rasters only: an uploaded SVG is script-capable
# and would be served from the storage CDN under our own deployment, which
# is the classic stored-XSS vector. 1MB is far below the 4.5MB serverless
# request-body limit and still allows a high-resolution mark.
MAX_LOGO_BYTES = 1_000_000
MAX_LOGO_BASE64_CHARS = 1_400_000
ALLOWED_LOGO_CONTENT_TYPES = {"image/png", "image/jpeg", "image/webp"}

# Cooperative policy: the floor for a member's monthly contribution is a
# cooperative setting (settings.minimum_monthly_contribution), not a code
# constant -- see contributions.assert_meets_minimum for where it is enforced.


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


def validate_contribution_amount(value: Decimal) -> Decimal:
    """Shape only -- the cooperative floor depends on a database row, so it
    is enforced where the session is available (contributions.assert_meets_minimum)."""
    return validate_positive_amount(value)


def validate_contribution_amount_optional(value: Optional[Decimal]) -> Optional[Decimal]:
    if value is None:
        return value
    return validate_contribution_amount(value)


def validate_month(value: str) -> str:
    """Accepts only a month label ('YYYY-MM') -- what the printed payroll
    schedule, the payroll department and a repayment's payment month all
    key on. Pydantic names the field in the error, so the message stays
    generic. Stored normalized to the first day of that month."""
    if not isinstance(value, str):
        raise ValueError("Must be in YYYY-MM format")
    value = value.strip()
    if not MONTH_RE.match(value):
        raise ValueError("Must be in YYYY-MM format")
    return value


def month_start_from_label(value: str) -> date:
    year, month = validate_month(value).split("-")
    return date(int(year), int(month), 1)


def normalize_name_part(value: Optional[str]) -> Optional[str]:
    """Collapse whitespace so "  Ada " and "Ada" store identically. Blank
    parts become None: "no other names" is an absence, not an empty string."""
    if value is None:
        return None
    collapsed = " ".join(str(value).split())
    return collapsed or None


def compose_member_name(last_name: str, first_name: str, other_names: Optional[str]) -> str:
    """
    The one printed form of a member's name: "Last, First Other(s)".

    Stored in Member.name so every screen, report and search result prints
    the same order without each of them re-deriving it. Other names are
    kept in full here; abbreviating them is a presentation choice made by
    the greeting (frontend/lib/names.ts).
    """
    last = normalize_name_part(last_name) or ""
    first = normalize_name_part(first_name) or ""
    other = normalize_name_part(other_names)
    composed = f"{last}, {first}"
    return f"{composed} {other}" if other else composed


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


def validate_logo_content_type(value: str) -> str:
    if value not in ALLOWED_LOGO_CONTENT_TYPES:
        raise ValueError(
            f"Unsupported logo file type {value!r}. Allowed: {', '.join(sorted(ALLOWED_LOGO_CONTENT_TYPES))}"
        )
    return value


def validate_logo_base64(value: str) -> str:
    if len(value) > MAX_LOGO_BASE64_CHARS:
        raise ValueError("Logo file is too large (maximum 1 MB)")
    try:
        base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError):
        raise ValueError("Logo file is not valid base64-encoded data")
    return value


def detect_image_content_type(data: bytes) -> Optional[str]:
    """Sniff the magic bytes of an allowed raster image.

    The declared content type is convenience on the wire; what actually gets
    stored and served is decided here, so a renamed file cannot smuggle a
    different format (or an SVG) past the upload endpoint.
    """
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None
