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
    UniqueConstraint,
    Index,
    CheckConstraint,
)
from sqlalchemy import JSON as GenericJSON
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship

from .database import Base

# Portable JSON column type: uses native JSONB on Postgres (production /
# Neon), falls back to generic JSON elsewhere (e.g. SQLite in tests) so
# the test suite doesn't require a real Postgres instance just to
# exercise audit/idempotency logic.
JSONType = GenericJSON().with_variant(JSONB, "postgresql")


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
    next_of_kin_address = Column(String, nullable=True)
    next_of_kin_email = Column(String, nullable=True)
    next_of_kin_relationship = Column(String, nullable=True)

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

    interest_rate/tenure_months/flat_charge below are a DENORMALIZED
    CACHE of "whichever rate version is effective as of today" -- kept
    so the many places that read loan_type.interest_rate directly (the
    admin table, the member application form's default display, older
    code) don't all need to become date-aware. The actual source of
    truth for "what rate applied on a specific date" is
    LoanTypeRateVersion; any code computing a REAL loan (disbursement,
    application decision) must look up the version effective as of the
    relevant date via loan_calc.get_effective_terms(), not read
    these cached fields directly, since a rate change scheduled for a
    future date should not apply early, and a loan disbursed after a
    rate change should use the new rate even if approved earlier.
    """

    __tablename__ = "loan_types"
    __table_args__ = (
        CheckConstraint("interest_rate >= 0", name="ck_loan_types_interest_rate_nonnegative"),
        CheckConstraint("tenure_months > 0", name="ck_loan_types_tenure_months_positive"),
        CheckConstraint("flat_charge >= 0", name="ck_loan_types_flat_charge_nonnegative"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    name = Column(String, unique=True, nullable=False, index=True)
    description = Column(String, nullable=True)

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
    rate_versions = relationship(
        "LoanTypeRateVersion", back_populates="loan_type", cascade="all, delete-orphan"
    )


class LoanTypeRateVersion(Base):
    """
    Effective-dated rate history for a loan type. Editing a loan type's
    rate/tenure/flat_charge creates a NEW row here (with an admin-chosen
    effective_from date) rather than mutating LoanType in place, so a
    rate change can be scheduled for the future, and loans already
    disbursed under an older rate are unaffected (they store their own
    computed numbers permanently and never re-read this table).
    """

    __tablename__ = "loan_type_rate_versions"
    __table_args__ = (
        CheckConstraint(
            "interest_rate >= 0", name="ck_loan_type_rate_versions_interest_rate_nonnegative"
        ),
        CheckConstraint(
            "tenure_months > 0", name="ck_loan_type_rate_versions_tenure_months_positive"
        ),
        CheckConstraint("flat_charge >= 0", name="ck_loan_type_rate_versions_flat_charge_nonnegative"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    loan_type_id = Column(
        UUID(as_uuid=True), ForeignKey("loan_types.id", ondelete="CASCADE"), nullable=False
    )

    interest_rate = Column(Numeric(6, 4), nullable=False)
    tenure_months = Column(Integer, nullable=False)
    flat_charge = Column(Numeric(14, 2), nullable=False, default=0)

    effective_from = Column(Date, nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow)

    loan_type = relationship("LoanType", back_populates="rate_versions")


class Loan(Base):
    """
    One row per ACTUAL DISBURSEMENT -- this row does not exist until an
    admin disburses an approved application (see LoanApplication.disburse
    flow), even though the application may have been "approved" earlier.
    Replaces the ~59 monthly 'Loan Disbursement' tables in the original
    workbook.

    Interest-at-source model: interest is deducted from what's actually
    paid out, not added on top of what's repaid.
      interest_amount     = principal * effective interest_rate
      net_disbursed         = principal - interest_amount  (what the member actually receives)
      total_repayable        = principal + flat_charge  (flat_charge, if any, IS added -- it's
                               a processing fee, not interest; only interest is "at source")
      monthly_installment    = total_repayable / approved_tenure_months
      expected_end_date      = disbursement_date + tenure_months (EDATE equivalent)
    disbursement_date is always normalized to the 1st of the month in
    which disbursement actually happens (not the member's requested date,
    which is only a preference recorded on the application).
    """

    __tablename__ = "loans"
    __table_args__ = (
        CheckConstraint("principal > 0", name="ck_loans_principal_positive"),
        CheckConstraint("interest_amount >= 0", name="ck_loans_interest_amount_nonnegative"),
        CheckConstraint("net_disbursed >= 0", name="ck_loans_net_disbursed_nonnegative"),
        CheckConstraint("total_repayable > 0", name="ck_loans_total_repayable_positive"),
        CheckConstraint("monthly_installment > 0", name="ck_loans_monthly_installment_positive"),
        CheckConstraint("amount_repaid >= 0", name="ck_loans_amount_repaid_nonnegative"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    member_id = Column(
        UUID(as_uuid=True), ForeignKey("members.id", ondelete="CASCADE"), nullable=False
    )
    loan_type_id = Column(
        UUID(as_uuid=True), ForeignKey("loan_types.id"), nullable=False
    )

    principal = Column(Numeric(14, 2), nullable=False)
    interest_amount = Column(Numeric(14, 2), nullable=False)
    net_disbursed = Column(Numeric(14, 2), nullable=False)
    total_repayable = Column(Numeric(14, 2), nullable=False)
    monthly_installment = Column(Numeric(14, 2), nullable=False)

    disbursement_date = Column(Date, nullable=False)
    expected_end_date = Column(Date, nullable=False)

    # Snapshot of which account the money actually went to -- the
    # member's account on file, or a one-off alternate they specified on
    # this application (see LoanApplication.alternate_*).
    disbursement_bank_name = Column(String, nullable=True)
    disbursement_account_name = Column(String, nullable=True)
    disbursement_account_number = Column(String, nullable=True)

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
    repayments = relationship("LoanRepayment", back_populates="loan", cascade="all, delete-orphan")


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

class UserRole(str, enum.Enum):
    ADMIN = "admin"
    MEMBER = "member"


class AccountStatus(str, enum.Enum):
    """
    Explicit account lifecycle state (Phase 1, Section 7). Distinct from
    the legacy `is_active` boolean, which is retained for backward
    compatibility with existing code paths that already read it -- the
    two are kept in sync by the account-lifecycle service functions in
    `account_lifecycle.py` rather than by ad hoc assignment.

    PENDING      -- account created but not yet activated (e.g. a member
                    login that has never completed its forced first
                    password reset can be modeled as pending in a later
                    phase; currently new logins go straight to ACTIVE
                    with must_change_password=True).
    ACTIVE       -- normal login/API/financial access, subject to
                    permission checks.
    SUSPENDED    -- temporarily blocked (e.g. under investigation);
                    reversible by an authorized admin.
    DEACTIVATED  -- permanently disabled; a deactivated administrator
                    must immediately lose administrative authority.
    """

    PENDING = "pending"
    ACTIVE = "active"
    SUSPENDED = "suspended"
    DEACTIVATED = "deactivated"


class User(Base):
    """
    Login credentials, separate from Member/business data. Members log in
    with their PSN as the username; admins use a chosen username/email.
    An admin creates a member's login with a temporary password and
    must_change_password=True, forcing a reset on first successful login.
    """

    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("failed_login_count >= 0", name="ck_users_failed_login_count_nonnegative"),
    )

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

    # Legacy coarse flag -- kept because existing code (get_current_user,
    # email/report views, etc.) already reads it. Authoritative state now
    # lives in account_status; is_active is kept mirrored to
    # (account_status == ACTIVE) by account_lifecycle.py so nothing that
    # reads the old column silently goes stale.
    is_active = Column(Boolean, nullable=False, default=True)

    account_status = Column(
        Enum(AccountStatus, values_callable=lambda enum_cls: [e.value for e in enum_cls]),
        nullable=False,
        default=AccountStatus.ACTIVE,
    )
    status_reason = Column(String, nullable=True)
    status_changed_at = Column(DateTime, nullable=True)
    status_changed_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)

    # Super Admin: controlled configuration authority (Blueprint Section
    # 13). Bypasses the granular Office/Role/Permission checks below, but
    # every action a super admin takes is still authenticated,
    # authorized-by-flag, and audited like anything else -- this is NOT
    # an is_admin=true shortcut for ordinary staff, it is reserved for
    # the small number of accounts that genuinely need full
    # configuration authority (see migration notes / Change-Control C-1).
    is_super_admin = Column(Boolean, nullable=False, default=False)

    # --- Brute-force / account lockout tracking (Section 6) ---
    failed_login_count = Column(Integer, nullable=False, default=0)
    locked_until = Column(DateTime, nullable=True)
    last_login_at = Column(DateTime, nullable=True)
    last_failed_login_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    member = relationship("Member", back_populates="user")
    role_assignments = relationship(
        "UserRoleAssignment",
        back_populates="user",
        foreign_keys="UserRoleAssignment.user_id",
        cascade="all, delete-orphan",
    )
    sessions = relationship(
        "AuthSession",
        back_populates="user",
        foreign_keys="AuthSession.user_id",
        cascade="all, delete-orphan",
    )


# ---------------------------------------------------------------------------
# Office / Role / Permission (Phase 1, Sections 8-9)
#
# User -> Office/Position -> Role -> Permissions.
#
# Office and Role are DB-configured (not hard-coded), so a cooperative can
# add offices/roles without a source-code change. Permission is an atomic
# capability; the catalogue of *known* permission codes is defined in
# permissions_catalogue.py and seeded into this table by
# scripts/seed_permissions.py, but the table itself -- and which
# permissions a given Role grants -- is ordinary configuration data.
# ---------------------------------------------------------------------------


class Office(Base):
    """A cooperative-defined office/position (President, Treasurer, ...).
    Purely an identity/title grouping for accountability and reporting;
    authorization itself flows through Role -> Permission, not Office
    directly, since two different offices might legitimately share a
    role's permission set."""

    __tablename__ = "offices"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, unique=True, nullable=False, index=True)
    description = Column(String, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Permission(Base):
    """An atomic capability, e.g. 'loan.approve'. Rows are seeded from the
    approved Phase 1 permission catalogue (permissions_catalogue.py);
    new codes require a code change + reseed, but which roles hold a
    given permission is ordinary configuration."""

    __tablename__ = "permissions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code = Column(String, unique=True, nullable=False, index=True)
    category = Column(String, nullable=False)
    description = Column(String, nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow)


class Role(Base):
    """A reusable, cooperative-configurable bundle of permissions."""

    __tablename__ = "roles"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, unique=True, nullable=False, index=True)
    description = Column(String, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    permissions = relationship(
        "RolePermission", back_populates="role", cascade="all, delete-orphan"
    )


class RolePermission(Base):
    """Many-to-many Role <-> Permission grant."""

    __tablename__ = "role_permissions"
    __table_args__ = (UniqueConstraint("role_id", "permission_id", name="uq_role_permission"),)

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    role_id = Column(UUID(as_uuid=True), ForeignKey("roles.id", ondelete="CASCADE"), nullable=False)
    permission_id = Column(
        UUID(as_uuid=True), ForeignKey("permissions.id", ondelete="CASCADE"), nullable=False
    )

    role = relationship("Role", back_populates="permissions")
    permission = relationship("Permission")


class UserRoleAssignment(Base):
    """
    Grants a staff/admin User a Role, optionally attached to an Office
    they hold that role under. A user may hold more than one active
    assignment (e.g. Treasurer + a Loan Officer role). Historical
    assignments are never deleted on revocation -- revoked_at is set
    instead -- so a past action's audit event can still be traced back
    to "what office/role did this actor hold at the time" (Blueprint
    Section 13: "Historical actions must retain the actor's identity and
    office at the time of action"); the AuditEvent itself also snapshots
    actor_office_name/actor_role_name at write time for this reason,
    since a later revocation must not rewrite history.
    """

    __tablename__ = "user_role_assignments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    role_id = Column(UUID(as_uuid=True), ForeignKey("roles.id"), nullable=False)
    office_id = Column(UUID(as_uuid=True), ForeignKey("offices.id"), nullable=True)

    is_active = Column(Boolean, nullable=False, default=True)

    assigned_at = Column(DateTime, default=datetime.utcnow)
    assigned_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    revoked_at = Column(DateTime, nullable=True)
    revoked_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)

    user = relationship("User", back_populates="role_assignments", foreign_keys=[user_id])
    role = relationship("Role")
    office = relationship("Office")


# ---------------------------------------------------------------------------
# Auth sessions (Section 6-7: session/token lifecycle, credential
# revocation, immediate loss of authority on deactivation)
# ---------------------------------------------------------------------------


class AuthSession(Base):
    """
    One row per issued access token (identified by its JWT `jti` claim).
    Access tokens remain short-lived JWTs (unchanged), but tracking the
    session server-side lets us support real logout and immediate
    revocation (e.g. an admin force-logs-out a deactivated account)
    instead of just waiting for natural JWT expiry. get_current_user
    checks that the session referenced by the token's jti is still
    un-revoked and unexpired, in addition to decoding the JWT itself.
    """

    __tablename__ = "auth_sessions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    jti = Column(String, unique=True, nullable=False, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    issued_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=False)
    ip_address = Column(String, nullable=True)
    user_agent = Column(String, nullable=True)

    revoked_at = Column(DateTime, nullable=True)
    revoked_reason = Column(String, nullable=True)

    user = relationship("User", back_populates="sessions", foreign_keys=[user_id])


# ---------------------------------------------------------------------------
# Audit trail (Section 13-14)
# ---------------------------------------------------------------------------


class AuditEvent(Base):
    """
    Immutable audit-event log. Rows are append-only: there is
    deliberately no update/delete path exposed anywhere in the
    application code (see audit_service.py) -- protecting that
    invariant at the database-role/permission level as well is a
    deployment-hardening step for Phase 10, not a Phase 1 code change.

    previous_values/new_values are JSONB snapshots of only the fields
    that changed (not full-row dumps), with passwords/secrets always
    excluded -- see audit_service.redact().
    """

    __tablename__ = "audit_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    actor_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True, index=True)
    # Snapshot of the actor's display context at the time of the action,
    # so a later office/role change or revocation can't rewrite history.
    actor_username = Column(String, nullable=True)
    actor_office_name = Column(String, nullable=True)
    actor_role_names = Column(String, nullable=True)  # comma-joined, denormalized snapshot

    event_type = Column(String, nullable=False, index=True)  # e.g. "auth.login_failed"
    entity_type = Column(String, nullable=True, index=True)  # e.g. "loan_application"
    entity_id = Column(String, nullable=True, index=True)
    action = Column(String, nullable=False)  # e.g. "create", "update", "approve", "reject"

    previous_values = Column(JSONType, nullable=True)
    new_values = Column(JSONType, nullable=True)
    reason = Column(String, nullable=True)

    ip_address = Column(String, nullable=True)
    user_agent = Column(String, nullable=True)
    request_reference = Column(String, nullable=True)  # correlates to a request id if present

    timestamp = Column(DateTime, default=datetime.utcnow, index=True)


Index("ix_audit_events_entity", AuditEvent.entity_type, AuditEvent.entity_id)


# ---------------------------------------------------------------------------
# Idempotency foundation (Section 17)
# ---------------------------------------------------------------------------


class IdempotencyRecord(Base):
    """
    Generic idempotency store. A state-changing endpoint decorated with
    `idempotent()` (see idempotency.py) hashes the request body and
    looks up (user_id, endpoint, idempotency_key). If a completed record
    exists with a matching request hash, the cached response is
    replayed instead of re-running the operation; a mismatched request
    hash under the same key is rejected (409) rather than silently
    executed, since that indicates client-side key reuse across a
    different request. `endpoint` plus `idempotency_key` are unique per
    user so keys can't collide across unrelated operations or users.
    """

    __tablename__ = "idempotency_records"
    __table_args__ = (
        UniqueConstraint("user_id", "endpoint", "idempotency_key", name="uq_idempotency_scope"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    endpoint = Column(String, nullable=False)
    idempotency_key = Column(String, nullable=False)
    request_hash = Column(String, nullable=False)

    status_code = Column(Integer, nullable=True)
    response_body = Column(JSONType, nullable=True)
    completed_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)


# ---------------------------------------------------------------------------
# Loan Applications
# ---------------------------------------------------------------------------

class LoanApplicationStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    CANCELLED = "cancelled"


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
    __table_args__ = (
        CheckConstraint("requested_amount > 0", name="ck_loan_applications_requested_amount_positive"),
        CheckConstraint(
            "approved_amount IS NULL OR approved_amount > 0",
            name="ck_loan_applications_approved_amount_positive",
        ),
        CheckConstraint("form_fee_amount >= 0", name="ck_loan_applications_form_fee_nonnegative"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    member_id = Column(
        UUID(as_uuid=True), ForeignKey("members.id", ondelete="CASCADE"), nullable=False
    )
    loan_type_id = Column(UUID(as_uuid=True), ForeignKey("loan_types.id"), nullable=False)

    requested_amount = Column(Numeric(14, 2), nullable=False)
    approved_amount = Column(Numeric(14, 2), nullable=True)

    # Tenure negotiation: a member may request a tenure shorter than (or
    # equal to) the loan type's default; an admin reviews and sets
    # approved_tenure_months at decision time (may match the request,
    # differ, or fall back to the default -- tenure_decision_reason
    # explains it if the admin didn't simply grant what was requested).
    # Repayment math always uses approved_tenure_months once set.
    requested_tenure_months = Column(Integer, nullable=True)
    approved_tenure_months = Column(Integer, nullable=True)
    tenure_decision_reason = Column(String, nullable=True)

    # Member's stated preference only -- the actual disbursement_date on
    # the resulting Loan is controlled by when an admin disburses it
    # (normalized to the 1st of that month), not this field.
    preferred_disbursement_date = Column(Date, nullable=True)

    # Where the money should go: the member's account on file by default,
    # or a one-off alternate for this loan only (not saved to the
    # member's profile). Structured (not a single free-text field) so
    # the disbursing admin can verify the account belongs to who they
    # think it does.
    use_default_account = Column(Boolean, nullable=False, default=True)
    alternate_bank_name = Column(String, nullable=True)
    alternate_account_name = Column(String, nullable=True)
    alternate_account_number = Column(String, nullable=True)

    # Cancellation: a member can cancel (forfeiting the form fee -- no
    # refund) any application that hasn't been disbursed yet, i.e. still
    # PENDING, or APPROVED but resulting_loan_id is still null. Once
    # cancelled, cancelled_at records when; the fee is simply not
    # refunded (no separate "forfeited" flag needed -- CANCELLED status
    # itself implies it).
    cancelled_at = Column(DateTime, nullable=True)

    # Reapply: when an admin rejects a loan DECISION (not a payment
    # rejection -- those can't be reapplied without a fresh application
    # regardless), they choose whether the member may submit a fresh
    # application referencing this one. Defaults to True (the common
    # case -- fixable issues like wrong amount) so an admin only has to
    # deliberately flip it for genuine non-qualification cases. A
    # reapplication is a brand new LoanApplication row (new payment
    # required) -- reapplied_from_id just links back for traceability.
    can_reapply = Column(Boolean, nullable=False, default=True)
    reapplied_from_id = Column(
        UUID(as_uuid=True), ForeignKey("loan_applications.id"), nullable=True
    )

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
# Loan Repayments (member-initiated servicing of an active loan)
# ---------------------------------------------------------------------------

class RepaymentVerificationStatus(str, enum.Enum):
    AWAITING_VERIFICATION = "awaiting_verification"
    VERIFIED = "verified"
    REJECTED = "rejected"


class LoanRepayment(Base):
    """
    A member's claim of having made a repayment toward an active loan,
    with proof (bank reference + receipt), verified by an admin before
    it actually increases Loan.amount_repaid. Mirrors the same
    payment-proof pattern as the loan-application form fee, applied here
    to ongoing servicing instead of the initial application.
    """

    __tablename__ = "loan_repayments"
    __table_args__ = (
        CheckConstraint("amount_claimed > 0", name="ck_loan_repayments_amount_claimed_positive"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    loan_id = Column(UUID(as_uuid=True), ForeignKey("loans.id", ondelete="CASCADE"), nullable=False)
    member_id = Column(UUID(as_uuid=True), ForeignKey("members.id", ondelete="CASCADE"), nullable=False)

    amount_claimed = Column(Numeric(14, 2), nullable=False)
    payment_reference = Column(String, nullable=False)
    receipt_image_base64 = Column(Text, nullable=False)
    receipt_content_type = Column(String, nullable=False)

    status = Column(
        Enum(RepaymentVerificationStatus, values_callable=lambda enum_cls: [e.value for e in enum_cls]),
        nullable=False,
        default=RepaymentVerificationStatus.AWAITING_VERIFICATION,
    )
    rejection_reason = Column(String, nullable=True)
    verified_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    verified_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    loan = relationship("Loan", back_populates="repayments")


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
    __table_args__ = (
        CheckConstraint("loan_form_fee >= 0", name="ck_settings_loan_form_fee_nonnegative"),
    )

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
