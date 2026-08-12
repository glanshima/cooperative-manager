import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Column,
    String,
    Integer,
    Boolean,
    DateTime,
    Date,
    Numeric,
    Enum,
    ForeignKey,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from .database import Base


class MemberStatus(str, enum.Enum):
    FINANCIAL = "financial"
    NON_FINANCIAL = "non_financial"


class Gender(str, enum.Enum):
    MALE = "Male"
    FEMALE = "Female"
    OTHER = "Other"


class Member(Base):
    """
    Mirrors membersTable from the original spreadsheet:
    S/No, NAME, PSN, BANK NAME, ACCOUNT NUMBER, GENDER, DEPARTMENT,
    PHONE, EMAIL, NEXT OF KIN, N.O.K PHONE, STATUS
    """

    __tablename__ = "members"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # PSN = Personnel/Staff Number, the unique staff identifier used
    # throughout the spreadsheet for lookups (VLOOKUP/XLOOKUP key)
    psn = Column(String, unique=True, nullable=False, index=True)

    name = Column(String, nullable=False, index=True)
    bank_name = Column(String, nullable=True)
    account_number = Column(String, nullable=True)
    gender = Column(Enum(Gender), nullable=True)
    department = Column(String, nullable=True)
    phone = Column(String, nullable=True)
    email = Column(String, nullable=True)
    next_of_kin = Column(String, nullable=True)
    next_of_kin_phone = Column(String, nullable=True)

    # STATUS in the spreadsheet: 1 = financial member, else non-financial
    status = Column(Enum(MemberStatus), nullable=False, default=MemberStatus.FINANCIAL)

    # Admin-set manual flag (not a computed salary ratio -- see models.py
    # note near LoanApplication) marking a member as too loan-burdened to
    # take on further loans right now. restriction_reason is free text for
    # the admin's own note (e.g. "already repaying 3 active loans").
    loan_restricted = Column(Boolean, nullable=False, default=False)
    restriction_reason = Column(String, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    loans = relationship("Loan", back_populates="member", cascade="all, delete-orphan")
    loan_applications = relationship(
        "LoanApplication", back_populates="member", cascade="all, delete-orphan"
    )
    user = relationship("User", back_populates="member", uselist=False)


class LoanStatus(str, enum.Enum):
    ACTIVE = "active"
    COMPLETED = "completed"
    DEFAULTED = "defaulted"


# NOTE on Postgres enums: by default, SQLAlchemy's Enum column stores the
# Python enum's NAME (e.g. "ACTIVE"), not its .value ("active"), which
# caused repeated migration failures on MemberStatus/Gender (had to send
# "MALE"/"FINANCIAL" instead of the intuitive "Male"/"financial"). LoanStatus
# uses values_callable below to store .value directly instead, so migration
# scripts can just pass "active"/"completed"/"defaulted" as expected. Any
# new enum added to this file should do the same unless there's a reason
# to match the older Member/Gender behavior.


class LoanType(Base):
    """
    Mirrors the 'Loan Types' sheet: each loan product has its own
    interest rate and repayment tenure (e.g. Capital, Short, Quick,
    Item, CR&O loans in the original workbook).
    """

    __tablename__ = "loan_types"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    name = Column(String, unique=True, nullable=False, index=True)

    # Stored as a decimal fraction, e.g. 0.15 for 15%. Numeric avoids
    # floating point drift when computing interest on large principals.
    interest_rate = Column(Numeric(6, 4), nullable=False)

    # Repayment period in months, used to compute the monthly installment
    tenure_months = Column(Integer, nullable=False)

    is_active = Column(Boolean, default=True, nullable=False)

    # Flat charge on top of interest, e.g. the workbook's Item Loan has a
    # 500 flat processing charge in addition to its interest rate. Zero
    # for loan types that don't have one.
    flat_charge = Column(Numeric(14, 2), nullable=False, default=0)

    # Whether members can self-apply for this loan type through their
    # dashboard. Admin-only loan types (e.g. still being configured, or
    # deliberately staff-disbursed only) stay False.
    open_for_application = Column(Boolean, nullable=False, default=False)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    loans = relationship("Loan", back_populates="loan_type")
    loan_applications = relationship("LoanApplication", back_populates="loan_type")


class Loan(Base):
    """
    One row per loan disbursement. Replaces the ~59 monthly
    'Loan Disbursement' tables in the original workbook with a single
    time-series table filtered by disbursement_date.

    Interest and repayment figures are computed once at disbursement
    time and stored, mirroring the spreadsheet's IFS-based formulas:
      interest_amount   = principal * loan_type.interest_rate
      total_repayable    = principal + interest_amount
      monthly_installment = total_repayable / loan_type.tenure_months
      expected_end_date   = disbursement_date + tenure_months (EDATE equivalent)
    """

    __tablename__ = "loans"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    member_id = Column(
        UUID(as_uuid=True), ForeignKey("members.id", ondelete="CASCADE"), nullable=False
    )
    loan_type_id = Column(
        UUID(as_uuid=True), ForeignKey("loan_types.id"), nullable=False
    )

    principal = Column(Numeric(14, 2), nullable=False)
    interest_amount = Column(Numeric(14, 2), nullable=False)
    total_repayable = Column(Numeric(14, 2), nullable=False)
    monthly_installment = Column(Numeric(14, 2), nullable=False)

    disbursement_date = Column(Date, nullable=False)
    expected_end_date = Column(Date, nullable=False)

    # Running total of repayments made so far; balance = total_repayable - amount_repaid
    amount_repaid = Column(Numeric(14, 2), nullable=False, default=0)

    status = Column(
        Enum(LoanStatus, values_callable=lambda enum_cls: [e.value for e in enum_cls]),
        nullable=False,
        default=LoanStatus.ACTIVE,
    )

    notes = Column(String, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    member = relationship("Member", back_populates="loans")
    loan_type = relationship("LoanType", back_populates="loans")
    application = relationship("LoanApplication", back_populates="resulting_loan", uselist=False)


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

class UserRole(str, enum.Enum):
    ADMIN = "admin"
    MEMBER = "member"


class User(Base):
    """
    Login credentials, separate from Member/business data. Members log in
    with their PSN as the username; admins use a chosen username/email.
    An admin creates a member's login with a temporary password and
    must_change_password=True, forcing a reset on first successful login.
    """

    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # For members this is set to their PSN at creation time (kept as its
    # own column, rather than joining through Member every login, so a
    # member's username survives even if their PSN were ever changed).
    username = Column(String, unique=True, nullable=False, index=True)

    password_hash = Column(String, nullable=False)

    role = Column(
        Enum(UserRole, values_callable=lambda enum_cls: [e.value for e in enum_cls]),
        nullable=False,
    )

    # Null for admin accounts; set for member accounts.
    member_id = Column(
        UUID(as_uuid=True), ForeignKey("members.id", ondelete="CASCADE"), nullable=True, unique=True
    )

    must_change_password = Column(Boolean, nullable=False, default=True)

    is_active = Column(Boolean, nullable=False, default=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    member = relationship("Member", back_populates="user")


# ---------------------------------------------------------------------------
# Loan Applications
# ---------------------------------------------------------------------------

class LoanApplicationStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class PaymentVerificationStatus(str, enum.Enum):
    AWAITING_VERIFICATION = "awaiting_verification"
    VERIFIED = "verified"
    REJECTED = "rejected"


class LoanApplication(Base):
    """
    A member's self-service loan request, reviewed by an admin before it
    becomes an actual Loan. The approved_amount can differ from
    requested_amount (an admin may approve a smaller amount than asked).

    Payment gating: a member must pay a fixed loan-form fee and upload
    proof (bank transfer reference + receipt image) before their
    application is even reviewable. payment_status and status
    (the loan decision) are deliberately separate state machines --
    a rejected *payment* (bad receipt) is a different thing from a
    rejected *loan* (payment fine, but the loan itself was declined),
    and conflating them into one status would lose that distinction in
    reporting. The application only becomes actionable for a loan
    decision once payment_status == VERIFIED.

    was_restricted_at_submission / restriction_reason_snapshot capture the
    member's loan_restricted state *at the time they applied*, so an
    admin reviewing the application later sees the flag that was true
    when it was submitted, even if the member's restriction is toggled
    off afterward (e.g. after taking corrective action).
    """

    __tablename__ = "loan_applications"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    member_id = Column(
        UUID(as_uuid=True), ForeignKey("members.id", ondelete="CASCADE"), nullable=False
    )
    loan_type_id = Column(UUID(as_uuid=True), ForeignKey("loan_types.id"), nullable=False)

    requested_amount = Column(Numeric(14, 2), nullable=False)
    approved_amount = Column(Numeric(14, 2), nullable=True)

    status = Column(
        Enum(LoanApplicationStatus, values_callable=lambda enum_cls: [e.value for e in enum_cls]),
        nullable=False,
        default=LoanApplicationStatus.PENDING,
    )

    member_notes = Column(String, nullable=True)  # member's own note on the application
    admin_notes = Column(String, nullable=True)  # admin's reasoning on approval/rejection

    was_restricted_at_submission = Column(Boolean, nullable=False, default=False)
    restriction_reason_snapshot = Column(String, nullable=True)

    # --- Loan-form fee payment, required before an application is reviewable ---
    form_fee_amount = Column(Numeric(14, 2), nullable=False)  # snapshot of Settings.loan_form_fee at submission
    payment_reference = Column(String, nullable=False)  # bank transfer reference number
    receipt_image_base64 = Column(Text, nullable=False)
    receipt_content_type = Column(String, nullable=False)  # e.g. "image/jpeg", "application/pdf"

    payment_status = Column(
        Enum(PaymentVerificationStatus, values_callable=lambda enum_cls: [e.value for e in enum_cls]),
        nullable=False,
        default=PaymentVerificationStatus.AWAITING_VERIFICATION,
    )
    payment_verified_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    payment_verified_at = Column(DateTime, nullable=True)
    payment_rejection_reason = Column(String, nullable=True)

    reviewed_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    reviewed_at = Column(DateTime, nullable=True)

    resulting_loan_id = Column(
        UUID(as_uuid=True), ForeignKey("loans.id"), nullable=True, unique=True
    )

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    member = relationship("Member", back_populates="loan_applications")
    loan_type = relationship("LoanType", back_populates="loan_applications")
    resulting_loan = relationship("Loan", back_populates="application")


# ---------------------------------------------------------------------------
# Settings (single-row table for now; see README for the multi-tenant note)
# ---------------------------------------------------------------------------

class LoanRestrictionBehavior(str, enum.Enum):
    BLOCK = "block"
    WARN = "warn"


class Settings(Base):
    """
    Single-row table of admin-configurable toggles. Read on every relevant
    request rather than cached, since this app's traffic is low enough
    that a fresh query per request costs nothing meaningful, and it avoids
    a whole class of "toggle changed but cache is stale" bugs.
    """

    __tablename__ = "settings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    loan_restriction_behavior = Column(
        Enum(LoanRestrictionBehavior, values_callable=lambda enum_cls: [e.value for e in enum_cls]),
        nullable=False,
        default=LoanRestrictionBehavior.WARN,
    )

    # Fixed fee a member must pay (and upload proof of) before a loan
    # application is even reviewable. Same amount regardless of loan type.
    loan_form_fee = Column(Numeric(14, 2), nullable=False, default=0)

    members_module_enabled = Column(Boolean, nullable=False, default=True)
    loans_module_enabled = Column(Boolean, nullable=False, default=True)
    deductions_module_enabled = Column(Boolean, nullable=False, default=True)
    cashbook_module_enabled = Column(Boolean, nullable=False, default=True)
    dividends_module_enabled = Column(Boolean, nullable=False, default=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
