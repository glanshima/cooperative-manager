import enum
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional

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
    text,
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

    # The printed name: "Last, First Other(s)" -- the single field every
    # screen and report reads. It is composed from the parts below when
    # they are supplied, so the registration form can capture the name in
    # its three pieces without any caller re-deriving the print order.
    name = Column(String, nullable=False, index=True)
    first_name = Column(String, nullable=True)
    last_name = Column(String, nullable=True)
    other_names = Column(String, nullable=True)
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

    # Membership exit (POST /api/members/{id}/withdraw). Non-null means the
    # member formally left the cooperative on that date. This is what
    # distinguishes a withdrawn member whose loan is still being recovered
    # through payroll from one who merely fell behind on contributions
    # (status flipped to non_financial, exit date still NULL) -- the
    # deduction queue labels the two differently.
    membership_exit_date = Column(Date, nullable=True)
    membership_exit_reason = Column(String, nullable=True)

    # The agreed monthly contribution payroll deducts (floor:
    # settings.minimum_monthly_contribution). NULL means "not on file
    # yet", which is where every member imported from the spreadsheet
    # starts: an officer bootstraps it once, and every later change goes
    # through a ContributionChangeRequest so the deducted amount is never
    # edited silently.
    monthly_contribution_amount = Column(Numeric(14, 2), nullable=True)
    # First payroll month the stored amount applies to. Approval is never
    # retroactive -- confirmed deduction lines keep what was actually
    # deducted, so a later change cannot rewrite savings history.
    contribution_effective_from = Column(Date, nullable=True)

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
    # Bug fix (Phase 0 assessment, 2026-08-30): this used to be a single
    # `user = relationship("User", back_populates="member", uselist=False)`,
    # which assumed at most one User row could ever reference a given
    # member_id. That was true when it was written, but the Controlled
    # Remediation pass's partial unique indexes (see the migration
    # scripts/manual_migration_2026_08_controlled_remediation_user_member_link.sql)
    # deliberately made it possible for TWO User rows to reference the
    # same member_id at once -- one role='member' self-service login,
    # one role='admin' account linked for conflict-of-interest checking
    # (self_conflict.py). The old relationship was never updated to
    # match, so calling member.user with both rows present would have
    # raised a SQLAlchemy "multiple rows returned for uselist=False
    # relationship" error the first time any code path actually used it
    # (nothing did yet -- this was a dormant bug, not an active one).
    #
    # HOTFIX 2026-08-30: the first attempt at this fix used two
    # SQLAlchemy relationship()s with a custom string primaryjoin
    # (filtering by role). That could not be verified in the sandbox
    # this was built in (no SQLAlchemy installed, no network to install
    # it), and it broke mapper configuration in production -- SQLAlchemy
    # configures ALL mapped relationships together the first time ANY
    # query runs, so a bad relationship on Member took down completely
    # unrelated endpoints too (login included, despite login never
    # touching Member at all). Reverted to plain, explicit query methods
    # below instead: no relationship() at all, so there is nothing for
    # mapper configuration to resolve or get wrong -- these only run
    # when actually called, with an explicit db session, like any other
    # query in this codebase.
    def get_member_login_user(self, db):
        """The role='member' self-service User for this Member, if any."""
        return (
            db.query(User)
            .filter(User.member_id == self.id, User.role == UserRole.MEMBER)
            .first()
        )

    def get_admin_login_user(self, db):
        """The role='admin' User linked to this Member for conflict-of-
        interest checking (self_conflict.py), if any."""
        return (
            db.query(User)
            .filter(User.member_id == self.id, User.role == UserRole.ADMIN)
            .first()
        )


# ---------------------------------------------------------------------------
# Member-to-Member relationships (Member Relationship / Next-of-Kin
# Controlled Remediation, 2026-09)
#
# Distinct from the pre-existing free-text next_of_kin/next_of_kin_phone/
# next_of_kin_address/next_of_kin_email/next_of_kin_relationship columns
# on Member above, which remain exactly as they were for a Next of Kin
# who is NOT themselves a cooperative member (Section 2 of the
# remediation prompt: "manual next-of-kin details" path). This table is
# the authoritative record for the OTHER case -- a Next of Kin who IS
# also a cooperative Member -- and is deliberately a first-class,
# reusable relationship model (member_id / related_member_id / type)
# rather than a single next_of_kin_member_id FK bolted onto Member,
# since the remediation prompt frames Next-of-Kin as the first of
# potentially several member-to-member relationship types this
# foundation needs to support later (e.g. a future
# guarantor/co-signer/household relationship), and a generic table
# avoids a schema change for each new type.
# ---------------------------------------------------------------------------


class RelationshipType(str, enum.Enum):
    NEXT_OF_KIN = "next_of_kin"


class RelationshipStatus(str, enum.Enum):
    ACTIVE = "active"
    REMOVED = "removed"


class MemberRelationship(Base):
    """
    A directed member-to-member relationship (currently only
    next_of_kin), used both to record "who is this member's Next of
    Kin, if that person is also a cooperative member" and, when
    conflict_of_interest is set, as the conflict-of-interest pairing
    that self_conflict.require_no_member_conflict() enforces on
    administrative actions between the two members (Section 12 of the
    remediation prompt).

    DIRECTION: member_id is the member the relationship is recorded
    FOR (e.g. the member filling out their own Next-of-Kin details);
    related_member_id is the OTHER member (the Next of Kin). Conflict
    lookups (has_member_conflict in member_relationships.py) check BOTH
    directions from a single row -- there is deliberately no mirrored
    reverse row, so "A's NOK is B" and any future reverse-direction
    query never risk drifting out of sync with each other.

    SELF-REFERENCE: a member can never be their own Next of Kin. This
    is enforced twice -- a DB-level CHECK constraint below (defense in
    depth, matching this codebase's existing pattern of CHECK
    constraints backing up application-level validation -- see the
    Phase 1 DB integrity constraints migration) and, primarily, an
    explicit check in the router before the row is ever inserted (see
    routers/members.py), so the rejection is a clean 409 with a
    specific message rather than a raw IntegrityError.

    AT MOST ONE ACTIVE next_of_kin PER member: enforced by the partial
    unique index below (member_id, relationship_type WHERE status =
    'active'). Inspection finding, not an invented rule: the
    pre-existing Member.next_of_kin* columns are a single set of
    fields (not a list), implying this cooperative's data model has
    always treated Next of Kin as one person per member -- this
    remediation preserves that same single-NOK shape for the
    member-linked path rather than introducing multiplicity the
    existing manual-entry path never had. Changing to a DIFFERENT
    related member is handled as remove-old-row + create-new-row (see
    member_relationships.py), not an in-place related_member_id
    update, so the audit trail retains who the previous Next of Kin
    was and when the change happened (Section 17 of the remediation
    prompt).

    HISTORY IS NEVER HARD-DELETED: removing a relationship (member
    reverts to a non-member Next of Kin, or their linked Next of Kin
    changes) sets status=REMOVED + removed_at/removed_by_user_id
    rather than deleting the row -- consistent with this codebase's
    existing Financial History Protection precedent (see
    delete_member's Change-Control C-2 docstring) applied here to
    relationship history instead of financial history.
    """

    __tablename__ = "member_relationships"
    __table_args__ = (
        CheckConstraint(
            "member_id != related_member_id",
            name="ck_member_relationships_no_self_reference",
        ),
        Index(
            "ux_member_relationships_one_active_per_type",
            "member_id",
            "relationship_type",
            unique=True,
            postgresql_where=text("status = 'active'"),
        ),
        Index("ix_member_relationships_related_member_id", "related_member_id"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    member_id = Column(
        UUID(as_uuid=True), ForeignKey("members.id", ondelete="CASCADE"), nullable=False, index=True
    )
    related_member_id = Column(
        UUID(as_uuid=True), ForeignKey("members.id", ondelete="CASCADE"), nullable=False
    )

    relationship_type = Column(
        Enum(RelationshipType, values_callable=lambda enum_cls: [e.value for e in enum_cls]),
        nullable=False,
        default=RelationshipType.NEXT_OF_KIN,
    )

    # Marks whether this relationship is treated as a conflict-of-interest
    # pairing by require_no_member_conflict (self_conflict.py). True by
    # default for next_of_kin (a Next of Kin is the clearest possible
    # conflict case); setting it False leaves the relationship recorded
    # for display/history while authorizing the two members to act on
    # each other's records.
    conflict_of_interest = Column(Boolean, nullable=False, default=True)

    status = Column(
        Enum(RelationshipStatus, values_callable=lambda enum_cls: [e.value for e in enum_cls]),
        nullable=False,
        default=RelationshipStatus.ACTIVE,
    )

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)

    removed_at = Column(DateTime, nullable=True)
    removed_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)

    # No relationship()s here, deliberately -- same rationale as
    # Member.get_member_login_user()/get_admin_login_user() above
    # (Section N hotfix lesson: a custom-disambiguation relationship()
    # broke mapper configuration app-wide in production once already).
    # This table has TWO foreign keys into members.id (member_id,
    # related_member_id), which would need foreign_keys=[...]
    # disambiguation on any relationship() declared here or back on
    # Member -- plain query methods avoid that mapper-configuration
    # surface entirely and are used everywhere else in this codebase
    # for anything beyond a single, unambiguous FK.
    def get_member(self, db):
        return db.query(Member).filter(Member.id == self.member_id).first()

    def get_related_member(self, db):
        return db.query(Member).filter(Member.id == self.related_member_id).first()


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


class InterestDeductionMode(str, enum.Enum):
    """How the interest on a loan is recovered from the member.

    AT_SOURCE: deducted from the payout; the member repays the principal.
    SPREAD_OVER_TENURE: full principal paid out; interest repaid in level
    instalments across the whole tenure.
    SPREAD_FIRST_MONTHS: full principal paid out; the interest is added to
    the instalment for the first N months only.
    """

    AT_SOURCE = "at_source"
    SPREAD_OVER_TENURE = "spread_over_tenure"
    SPREAD_FIRST_MONTHS = "spread_first_months"


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

    # Processing fee charged for this loan type. It is paid separately by
    # the member (bank transfer + receipt, verified like the application
    # form fee) and is NEVER part of the loan: it changes neither the
    # payout, the total repayable, nor the instalment. Zero when the type
    # has no fee.
    flat_charge = Column(Numeric(14, 2), nullable=False, default=0)

    # Interest recovery override for this type (denormalized cache of the
    # effective rate version, same as interest_rate above). NULL means
    # "use the cooperative default" from Settings.
    interest_mode = Column(
        Enum(InterestDeductionMode, values_callable=lambda enum_cls: [e.value for e in enum_cls]),
        nullable=True,
    )
    # Only meaningful for SPREAD_FIRST_MONTHS; NULL means inherit the
    # cooperative default.
    interest_spread_months = Column(Integer, nullable=True)

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

    # Contractual repayment shape as of this version: changing how interest
    # is recovered is a term change, so it is effective-dated like the
    # rate itself. NULL = inherit the cooperative default (for mode) or
    # that default's spread months.
    interest_mode = Column(
        Enum(InterestDeductionMode, values_callable=lambda enum_cls: [e.value for e in enum_cls]),
        nullable=True,
    )
    interest_spread_months = Column(Integer, nullable=True)

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

    Interest recovery is resolved at disbursement from the rate version
    effective that day (see loan_calc.compute_loan_terms); the resulting
    mode is snapshotted here so later configuration changes never rewrite
    an existing loan.

      interest_amount     = principal * effective interest_rate
      at source           net_disbursed = principal - interest, total = principal
      spread modes        net_disbursed = principal,          total = principal + interest
      SPREAD_FIRST_MONTHS additionally records interest_installment (the
      extra monthly amount during the first interest_spread_months) --
      monthly_installment stays the principal portion.
      expected_end_date   = disbursement_date + tenure_months (EDATE equivalent)

    The loan type's flat_charge is a fee paid separately and is not part
    of any of these figures; fee_amount only records what is owed outside
    the loan so the payment can be verified.
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
        CheckConstraint(
            "interest_installment >= 0", name="ck_loans_interest_installment_nonnegative"
        ),
        CheckConstraint("fee_amount >= 0", name="ck_loans_fee_amount_nonnegative"),
        # A member can hold at most one ACTIVE loan of each loan type.
        Index(
            "uq_loans_member_loan_type_active",
            "member_id",
            "loan_type_id",
            unique=True,
            postgresql_where=text("status = 'active'"),
            sqlite_where=text("status = 'active'"),
        ),
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

    # Snapshot of the resolved terms at disbursement. interest_installment
    # is the extra amount on each of the first interest_spread_months
    # instalments (SPREAD_FIRST_MONTHS only); zero otherwise.
    interest_mode = Column(
        Enum(InterestDeductionMode, values_callable=lambda enum_cls: [e.value for e in enum_cls]),
        nullable=False,
        default=InterestDeductionMode.AT_SOURCE,
    )
    interest_spread_months = Column(Integer, nullable=True)
    interest_installment = Column(Numeric(14, 2), nullable=False, default=0)

    # Fee owed separately from this loan (the loan type's flat_charge at
    # disbursement). Never part of the figures above.
    fee_amount = Column(Numeric(14, 2), nullable=False, default=0)

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
    fee_payments = relationship(
        "LoanFeePayment", back_populates="loan", cascade="all, delete-orphan"
    )

    @property
    def fee_status(self) -> str:
        """not_required | due | awaiting_verification | rejected | paid."""
        if not self.fee_amount or self.fee_amount <= 0:
            return "not_required"
        if any(p.status == FeePaymentStatus.VERIFIED for p in self.fee_payments):
            return "paid"
        if any(p.status == FeePaymentStatus.AWAITING_VERIFICATION for p in self.fee_payments):
            return "awaiting_verification"
        if any(p.status == FeePaymentStatus.REJECTED for p in self.fee_payments):
            return "rejected"
        return "due"

    @property
    def fee_rejection_reason(self):
        rejected = [p for p in self.fee_payments if p.status == FeePaymentStatus.REJECTED]
        if not rejected:
            return None
        return max(rejected, key=lambda p: p.created_at or datetime.min).rejection_reason


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

    User.member_id (Controlled Phase 1 Remediation, Section 1) links a
    User account to the Member record it belongs to, when the person
    behind the account is also a cooperative member -- this is the
    ONLY thing the conflict-of-interest guard (self_conflict.py) uses to
    decide whether an admin is acting on their own money. It is set
    explicitly and manually by another admin via the admin-users API
    (never inferred from name/email/phone -- see self_conflict.py's
    module docstring), and defaults to NULL for both new and pre-existing
    accounts until someone deliberately links one.

    A member-role self-service account (role=MEMBER) and an admin-role
    account (role=ADMIN) for the SAME underlying person are two separate
    User rows (they have different login credentials/paths -- PSN vs.
    admin username), and BOTH may legitimately reference the same
    member_id at once (an EXCO officer both self-serves as a member and
    acts with admin authority under a different login). What must never
    happen is *two* rows of the *same* role both claiming the same
    member_id -- that would be an ambiguous/duplicate mapping. The
    uniqueness constraint below is therefore scoped per-role (a partial
    unique index), not a single table-wide unique column -- see the
    Phase 1 DB integrity constraints migration and the dedicated
    Controlled-Remediation migration for the exact SQL.
    """

    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("failed_login_count >= 0", name="ck_users_failed_login_count_nonnegative"),
        Index(
            "ux_users_member_id_per_member_role",
            "member_id",
            unique=True,
            postgresql_where=text("role = 'member'"),
        ),
        Index(
            "ux_users_member_id_per_admin_role",
            "member_id",
            unique=True,
            postgresql_where=text("role = 'admin'"),
        ),
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

    # See the class docstring above (Controlled Phase 1 Remediation,
    # Section 1) -- NULL for any account not explicitly linked to a
    # member, including admin accounts by default. Uniqueness is
    # enforced per-role via the partial indexes in __table_args__, NOT
    # by a plain unique=True here (that would have blocked a member's
    # self-service account and their separate admin account from both
    # legitimately linking to the same member_id).
    member_id = Column(
        UUID(as_uuid=True), ForeignKey("members.id", ondelete="CASCADE"), nullable=True
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

    # No back_populates here (see Member.get_member_login_user() /
    # Member.get_admin_login_user() below, in the Member class) -- this
    # side (User -> Member) is unambiguous (each User has at most one
    # member_id), but the reverse (Member -> User) is NOT one-to-one
    # since the Controlled Remediation pass's partial unique indexes:
    # up to two User rows (one role='member', one role='admin') can
    # legitimately reference the same member_id at once. A plain
    # back_populates="user" with uselist=False on the Member side would
    # raise at runtime the moment both exist for the same member.
    member = relationship("Member")
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
    password_reset_tokens = relationship(
        "PasswordResetToken",
        back_populates="user",
        foreign_keys="PasswordResetToken.user_id",
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

    # Admin Identity Governance remediation (2026-08-31): whether an
    # account holding this role (via an active UserRoleAssignment) must
    # be linked to a Member (User.member_id != NULL). False by default --
    # not every admin/staff role represents a cooperative member (e.g.
    # System Administrator, Auditor); only roles that represent or act in
    # a capacity requiring an identifiable Member (EXCO/office roles like
    # Treasurer) should have this set True. Enforced in
    # routers/admin_users.py at role-assignment time and at unlink time
    # -- see _role_requires_member_link_active() there. No existing role
    # data is affected by adding this column (every pre-existing role
    # defaults to False, so no already-assigned role retroactively
    # becomes invalid).
    requires_member_link = Column(Boolean, nullable=False, default=False)

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
# Password Reset Tokens (Self-Service Password Recovery)
# ---------------------------------------------------------------------------


class PasswordResetToken(Base):
    """
    Stores cryptographically hashed, short-lived, single-use password
    recovery tokens. Raw tokens are generated via secrets.token_urlsafe(32)
    and sent via email; only their SHA-256 hex digest (token_hash) is stored
    here. On successful password reset, used_at is populated and all active
    AuthSession rows for the user are revoked.
    """

    __tablename__ = "password_reset_tokens"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    token_hash = Column(String, nullable=False, index=True)
    expires_at = Column(DateTime, nullable=False, index=True)
    used_at = Column(DateTime, nullable=True)
    attempt_count = Column(Integer, nullable=False, default=0)

    ip_address = Column(String, nullable=True)
    user_agent = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="password_reset_tokens", foreign_keys=[user_id])


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
# In-app notifications
# ---------------------------------------------------------------------------


class NotificationCategory(str, enum.Enum):
    LOAN = "loan"
    REPAYMENT = "repayment"
    CONTRIBUTION = "contribution"
    ACCOUNT = "account"
    SYSTEM = "system"


class Notification(Base):
    """
    One in-app notice for one user account.

    Rows are written in the SAME transaction as the state change they
    describe, so a member never sees a notification for something that
    was rolled back, and a committed change never loses its notice. The
    title/body are stored as rendered text rather than a template plus
    parameters: what the member was told must not change if wording or
    business logic changes later.

    There is deliberately no cross-user read path -- the router always
    filters on current_user.id, so a notification id alone is never
    enough to read or mark someone else's row.
    """

    __tablename__ = "notifications"
    __table_args__ = (
        Index("ix_notifications_user_created", "user_id", text("created_at DESC")),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    category = Column(
        Enum(NotificationCategory, values_callable=lambda enum_cls: [e.value for e in enum_cls]),
        nullable=False,
    )
    title = Column(String(200), nullable=False)
    body = Column(String(1000), nullable=True)
    # Member-facing in-app route the notice points at (e.g. "/dashboard").
    link_path = Column(String(255), nullable=True)

    is_read = Column(Boolean, nullable=False, default=False)
    read_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class NotificationPreference(Base):
    """
    One account's email switches, per optional category.

    Only categories whose email is genuinely optional get a column --
    account and security notices are deliberate and cannot be switched
    off. A missing row means "all defaults" (every optional email on),
    so the table stays empty until an account changes something.
    """

    __tablename__ = "notification_preferences"

    user_id = Column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    email_loan = Column(Boolean, nullable=False, default=True)
    email_repayment = Column(Boolean, nullable=False, default=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


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

    # The month the member actually paid, normalized to its first day.
    # verified_at is when an officer checked the proof, which can be a
    # different month entirely -- payroll prefill nets installments off
    # against THIS column so a member who paid by bank isn't deducted the
    # same installment again. Legacy rows are NULL (unknown month) and are
    # surfaced as a warning rather than guessed at.
    payment_month = Column(Date, nullable=True)

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
# Loan fee payments (the loan type's processing fee, paid separately)
# ---------------------------------------------------------------------------

class FeePaymentStatus(str, enum.Enum):
    AWAITING_VERIFICATION = "awaiting_verification"
    VERIFIED = "verified"
    REJECTED = "rejected"


class LoanFeePayment(Base):
    """
    Proof of payment of a loan's processing fee. The fee is cooperative
    income, charged outside the loan itself: a verified row never changes
    Loan.total_repayable, amount_repaid or the disbursed amount. It
    exists so the money can be reviewed now and reported as income by
    the cashbook once that module lands.
    """

    __tablename__ = "loan_fee_payments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    loan_id = Column(UUID(as_uuid=True), ForeignKey("loans.id", ondelete="CASCADE"), nullable=False)
    member_id = Column(UUID(as_uuid=True), ForeignKey("members.id", ondelete="CASCADE"), nullable=False)

    # Snapshot of Loan.fee_amount at submission so a later correction to
    # the loan never rewrites what this payment was for.
    amount = Column(Numeric(14, 2), nullable=False)
    payment_reference = Column(String, nullable=False)
    receipt_image_base64 = Column(Text, nullable=False)
    receipt_content_type = Column(String, nullable=False)

    status = Column(
        Enum(FeePaymentStatus, values_callable=lambda enum_cls: [e.value for e in enum_cls]),
        nullable=False,
        default=FeePaymentStatus.AWAITING_VERIFICATION,
    )
    rejection_reason = Column(String, nullable=True)
    verified_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    verified_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    loan = relationship("Loan", back_populates="fee_payments")
    member = relationship("Member")


# ---------------------------------------------------------------------------
# Monthly contribution amounts (the member's savings instalment)
# ---------------------------------------------------------------------------

class ContributionChangeRequestStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class ContributionChangeRequest(Base):
    """A member's application to increase or decrease their monthly
    contribution.

    Member.monthly_contribution_amount is what payroll actually deducts;
    this table is how that number changes. current_amount is a snapshot
    taken when the request was made, so the review screen and the audit
    trail still show what the member was moving from after approval has
    overwritten the member's stored value.

    Approval is never retroactive: effective_from is the first day of a
    future payroll month, and confirmed deduction lines keep the amount
    actually deducted (the savings ledger records those lines, not this
    column), so a change cannot rewrite savings history.

    One pending request per member -- the partial unique index below --
    because two competing amounts for the same payroll month cannot both
    be right. Decided requests stay as history.
    """

    __tablename__ = "contribution_change_requests"
    __table_args__ = (
        CheckConstraint(
            "requested_amount > 0", name="ck_contribution_change_requests_amount_positive"
        ),
        Index(
            "uq_contribution_change_requests_member_pending",
            "member_id",
            unique=True,
            postgresql_where=text("status = 'pending'"),
        ),
        Index("ix_contribution_change_requests_member_id", "member_id"),
        Index("ix_contribution_change_requests_status", "status"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    member_id = Column(
        UUID(as_uuid=True), ForeignKey("members.id", ondelete="CASCADE"), nullable=False
    )

    current_amount = Column(Numeric(14, 2), nullable=True)
    requested_amount = Column(Numeric(14, 2), nullable=False)
    reason = Column(Text, nullable=True)

    status = Column(
        Enum(
            ContributionChangeRequestStatus,
            values_callable=lambda enum_cls: [e.value for e in enum_cls],
        ),
        nullable=False,
        default=ContributionChangeRequestStatus.PENDING,
    )
    effective_from = Column(Date, nullable=True)

    requested_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    reviewed_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    reviewed_at = Column(DateTime, nullable=True)
    review_reason = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    member = relationship("Member")

    @property
    def member_name(self):
        return self.member.name if self.member else None

    @property
    def member_psn(self):
        return self.member.psn if self.member else None


# ---------------------------------------------------------------------------
# Payroll Deductions (monthly staff-payroll deduction ledger)
# ---------------------------------------------------------------------------

class PayrollDeductionStatus(str, enum.Enum):
    DRAFT = "draft"
    SUBMITTED = "submitted"
    CONFIRMED = "confirmed"
    NOT_DEDUCTED = "not_deducted"
    VOID = "void"


class PayrollDeductionLineCategory(str, enum.Enum):
    MONTHLY_CONTRIBUTION = "monthly_contribution"
    LOAN_REPAYMENT = "loan_repayment"
    # A catch-up on instalments missed in earlier months, for the loan this
    # line names. It credits Loan.amount_repaid exactly like LOAN_REPAYMENT
    # and is a separate category only so the printed schedule can show why a
    # month deducts more than one instalment instead of hiding it inside one.
    LOAN_ARREARS = "loan_arrears"
    OTHER = "other"


class DeductionWorklistEntryState(str, enum.Enum):
    """Which half of the queue the officer is looking at. Nothing is stored
    under this value -- it filters the worklist by whether the member
    already has a live record for the month."""

    PENDING = "pending"
    ENTERED = "entered"
    ALL = "all"


class PayrollDeduction(Base):
    """
    One member's month-end payroll deduction for one month: monthly
    contribution, repayments of specific loans, and any other requested
    deduction.

    Lifecycle (the printed schedule is what payroll actually acts on):
      draft -> submitted -> confirmed      (payroll deducted and remitted)
                         -> not_deducted   (payroll skipped it; member pays
                              by bank/cash and uses the existing repayment
                              evidence flow instead)
      any non-void status -> void          (append-only correction; voids a
                              confirmed record by reversing its loan credits)

    Loan.amount_repaid only changes at `confirmed` -- never when a
    deduction is drafted or submitted -- because until payroll actually
    remits, the cooperative has not received the money.
    """

    __tablename__ = "payroll_deductions"
    __table_args__ = (
        # One live record per member per month. Voided records are excluded
        # so a correction can be re-entered without deleting history.
        Index(
            "uq_payroll_deductions_member_month_active",
            "member_id",
            "deduction_month",
            unique=True,
            postgresql_where=text("status <> 'void'"),
            sqlite_where=text("status <> 'void'"),
        ),
        Index("ix_payroll_deductions_deduction_month", "deduction_month"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    member_id = Column(UUID(as_uuid=True), ForeignKey("members.id", ondelete="CASCADE"), nullable=False)

    # Always normalized to the first day of the month being deducted.
    deduction_month = Column(Date, nullable=False)
    payroll_reference = Column(String, nullable=True)
    note = Column(Text, nullable=True)

    status = Column(
        Enum(PayrollDeductionStatus, values_callable=lambda enum_cls: [e.value for e in enum_cls]),
        nullable=False,
        default=PayrollDeductionStatus.DRAFT,
    )

    created_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)

    submitted_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    submitted_at = Column(DateTime, nullable=True)

    confirmed_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    confirmed_at = Column(DateTime, nullable=True)

    not_deducted_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    not_deducted_at = Column(DateTime, nullable=True)
    not_deducted_reason = Column(Text, nullable=True)

    # Set when a submitted schedule is sent back to draft for correction.
    returned_at = Column(DateTime, nullable=True)
    return_reason = Column(Text, nullable=True)

    voided_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    voided_at = Column(DateTime, nullable=True)
    void_reason = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    member = relationship("Member")
    lines = relationship(
        "PayrollDeductionLine",
        back_populates="deduction",
        cascade="all, delete-orphan",
        order_by="PayrollDeductionLine.created_at",
    )

    def _total(self, category: PayrollDeductionLineCategory) -> Decimal:
        return sum((line.amount for line in self.lines if line.category == category), Decimal("0"))

    @property
    def contribution_total(self) -> Decimal:
        return self._total(PayrollDeductionLineCategory.MONTHLY_CONTRIBUTION)

    @property
    def loan_total(self) -> Decimal:
        return self._total(PayrollDeductionLineCategory.LOAN_REPAYMENT)

    @property
    def arrears_total(self) -> Decimal:
        return self._total(PayrollDeductionLineCategory.LOAN_ARREARS)

    @property
    def other_total(self) -> Decimal:
        return self._total(PayrollDeductionLineCategory.OTHER)

    @property
    def grand_total(self) -> Decimal:
        return sum((line.amount for line in self.lines), Decimal("0"))

    @property
    def member_name(self):
        return self.member.name if self.member else None

    @property
    def member_psn(self):
        return self.member.psn if self.member else None


class PayrollDeductionLine(Base):
    """
    One category amount inside a member's monthly deduction. Loan lines
    carry an explicit loan_id (the member's own allocation across loans);
    'other' lines carry a free-text label. A contribution line is posted
    to the member's savings ledger when the deduction is confirmed.
    """

    __tablename__ = "payroll_deduction_lines"
    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_payroll_deduction_lines_amount_positive"),
        # Every loan line (repayment or arrears) names its loan; only the
        # non-loan categories omit it. Naming categories positively instead
        # of listing loan ones keeps this in step with new loan line kinds.
        CheckConstraint(
            "(category NOT IN ('monthly_contribution', 'other') AND loan_id IS NOT NULL) "
            "OR (category IN ('monthly_contribution', 'other') AND loan_id IS NULL)",
            name="ck_payroll_deduction_lines_loan_link",
        ),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    deduction_id = Column(
        UUID(as_uuid=True), ForeignKey("payroll_deductions.id", ondelete="CASCADE"), nullable=False
    )

    category = Column(
        Enum(PayrollDeductionLineCategory, values_callable=lambda enum_cls: [e.value for e in enum_cls]),
        nullable=False,
    )
    loan_id = Column(UUID(as_uuid=True), ForeignKey("loans.id"), nullable=True)
    label = Column(String, nullable=True)
    amount = Column(Numeric(14, 2), nullable=False)

    # What the server computed this line should be, from the member's
    # stored contribution or the loan's installment net of that month's
    # verified repayments (see deduction_expectations.py). NULL means the
    # officer typed the amount with no expectation behind it. Always
    # derived server-side, never accepted from the client, so amount !=
    # expected_amount is a trustworthy signal of a deliberate override.
    expected_amount = Column(Numeric(14, 2), nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)

    deduction = relationship("PayrollDeduction", back_populates="lines")
    loan = relationship("Loan")

    @property
    def loan_type_name(self):
        if self.loan and self.loan.loan_type:
            return self.loan.loan_type.name
        return None


# ---------------------------------------------------------------------------
# Settings (single-row table for now; see README for the multi-tenant note)
# ---------------------------------------------------------------------------

class LoanRestrictionBehavior(str, enum.Enum):
    BLOCK = "block"
    WARN = "warn"


class LoanDefaultGraceMode(str, enum.Enum):
    """When an unpaid instalment turns into a default.

    NEXT_PAYROLL is the staff-cooperative rule: the member keeps the whole
    instalment month to pay, and the shortfall only becomes a default when
    the next payroll deduction is processed. DAYS uses a fixed window that
    starts when the instalment's month closes.
    """

    NEXT_PAYROLL = "next_payroll"
    DAYS = "days"


# Branding defaults, used both as column defaults and as the public
# branding fallback when no settings row exists yet.
DEFAULT_COOPERATIVE_NAME = "MACT Cooperative"
DEFAULT_COOPERATIVE_SHORT_NAME = "MACT"
DEFAULT_COOPERATIVE_MONOGRAM = "M"


class DividendBasis(str, enum.Enum):
    """What a member's share of the pool is proportional to.

    ``share_capital`` is part of the agreed policy vocabulary but has no
    member ledger behind it yet, so a run refuses it instead of guessing.
    """

    NONE = "none"
    NET_SAVINGS_CLOSING = "net_savings_closing"
    NET_SAVINGS_AVERAGE = "net_savings_average"
    DECLARED_RATE_ON_SAVINGS = "declared_rate_on_savings"
    SHARE_CAPITAL = "share_capital"
    PATRONAGE = "patronage"
    EQUAL = "equal"
    HYBRID = "hybrid"


class DividendPoolMode(str, enum.Enum):
    NET_INCOME_SHARE = "net_income_share"
    SAVINGS_PERCENT = "savings_percent"
    FIXED_AMOUNT = "fixed_amount"


class DividendRunStatus(str, enum.Enum):
    DRAFT = "draft"
    DECLARED = "declared"
    PAID = "paid"


class DividendRounding(str, enum.Enum):
    TWO_DP = "two_dp"
    WHOLE_CURRENCY = "whole_currency"


class DividendPayoutMethod(str, enum.Enum):
    CASH = "cash"
    BANK = "bank"


class DividendPaymentPolicy(str, enum.Enum):
    BANK = "bank"
    CASH = "cash"
    EITHER = "either"


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
        CheckConstraint(
            "loan_interest_spread_months IS NULL OR loan_interest_spread_months > 0",
            name="ck_settings_loan_interest_spread_months_positive",
        ),
        CheckConstraint(
            "minimum_monthly_contribution >= 0",
            name="ck_settings_minimum_contribution_nonnegative",
        ),
        CheckConstraint(
            "default_monthly_contribution >= 0",
            name="ck_settings_default_contribution_nonnegative",
        ),
        CheckConstraint(
            "loan_default_charge_pct >= 0 AND loan_default_charge_pct <= 100",
            name="ck_settings_loan_default_charge_pct_range",
        ),
        CheckConstraint(
            "loan_default_grace_days >= 0 AND loan_default_grace_days <= 365",
            name="ck_settings_loan_default_grace_days_range",
        ),
        CheckConstraint(
            "fiscal_year_start_month >= 1 AND fiscal_year_start_month <= 12",
            name="ck_settings_fiscal_year_start_month",
        ),
        CheckConstraint(
            "dividend_reserve_pct >= 0 AND dividend_reserve_pct <= 100"
            " AND dividend_honorarium_pct >= 0 AND dividend_honorarium_pct <= 100"
            " AND dividend_payout_pct >= 0 AND dividend_payout_pct <= 100"
            " AND dividend_hybrid_savings_pct >= 0 AND dividend_hybrid_savings_pct <= 100"
            " AND dividend_withholding_pct >= 0 AND dividend_withholding_pct <= 100",
            name="ck_settings_dividend_pct_ranges",
        ),
        CheckConstraint(
            "dividend_min_membership_months >= 0",
            name="ck_settings_dividend_min_months",
        ),
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

    # Cooperative-wide default for how loan interest is recovered. A loan
    # type's rate version may override it; NULL there means "use this".
    loan_interest_mode = Column(
        Enum(InterestDeductionMode, values_callable=lambda enum_cls: [e.value for e in enum_cls]),
        nullable=False,
        default=InterestDeductionMode.AT_SOURCE,
    )
    # Cooperative-wide default for SPREAD_FIRST_MONTHS.
    loan_interest_spread_months = Column(Integer, nullable=True)

    # The payroll contribution floor and the figure an officer is offered
    # when recording a member's amount. Both were fixed in code before the
    # cooperative-level policy slice; a cooperative that sets no floor
    # stores 0.
    minimum_monthly_contribution = Column(Numeric(14, 2), nullable=False, default=0)
    default_monthly_contribution = Column(Numeric(14, 2), nullable=False, default=0)

    # What happens when a member misses an instalment. The charge is raised
    # once per missed instalment; it is never taken out of savings.
    loan_default_charge_pct = Column(Numeric(5, 2), nullable=False, default=0)
    loan_default_grace_mode = Column(
        Enum(LoanDefaultGraceMode, values_callable=lambda enum_cls: [e.value for e in enum_cls]),
        nullable=False,
        default=LoanDefaultGraceMode.NEXT_PAYROLL,
    )
    loan_default_grace_days = Column(Integer, nullable=False, default=0)

    members_module_enabled = Column(Boolean, nullable=False, default=True)
    loans_module_enabled = Column(Boolean, nullable=False, default=True)
    deductions_module_enabled = Column(Boolean, nullable=False, default=True)
    # No cashbook or dividends module exists yet, so these start off: an
    # enabled switch for absent software reads to an admin as broken rather
    # than as a roadmap. Flip them here when the modules land.
    cashbook_module_enabled = Column(Boolean, nullable=False, default=False)
    dividends_module_enabled = Column(Boolean, nullable=False, default=False)

    # Dividend policy. A dividend appropriates surplus that has already
    # been earned -- reserve, honorarium and payout slices are percentages
    # of the year's surplus and are expected to add up to 100; the service
    # enforces that sum, the columns only bound each slice.
    fiscal_year_start_month = Column(Integer, nullable=False, default=1)
    dividend_basis = Column(
        Enum(DividendBasis, name="dividendbasis", values_callable=lambda enum_cls: [e.value for e in enum_cls]),
        nullable=False,
        default=DividendBasis.NONE,
    )
    dividend_pool_mode = Column(
        Enum(
            DividendPoolMode,
            name="dividendpoolmode",
            values_callable=lambda enum_cls: [e.value for e in enum_cls],
        ),
        nullable=False,
        default=DividendPoolMode.NET_INCOME_SHARE,
    )
    dividend_reserve_pct = Column(Numeric(5, 2), nullable=False, default=Decimal("4.70"))
    dividend_honorarium_pct = Column(Numeric(5, 2), nullable=False, default=Decimal("3.00"))
    dividend_payout_pct = Column(Numeric(5, 2), nullable=False, default=Decimal("92.30"))
    dividend_declared_rate_pct = Column(Numeric(5, 2), nullable=True)
    dividend_fixed_pool_amount = Column(Numeric(14, 2), nullable=True)
    dividend_hybrid_savings_pct = Column(Numeric(5, 2), nullable=False, default=Decimal("50.00"))
    dividend_min_membership_months = Column(Integer, nullable=False, default=0)
    dividend_include_exited = Column(Boolean, nullable=False, default=False)
    dividend_rounding = Column(
        Enum(
            DividendRounding,
            name="dividendrounding",
            values_callable=lambda enum_cls: [e.value for e in enum_cls],
        ),
        nullable=False,
        default=DividendRounding.TWO_DP,
    )
    dividend_withholding_pct = Column(Numeric(5, 2), nullable=False, default=0)
    dividend_payment_method = Column(
        Enum(
            DividendPaymentPolicy,
            name="dividendpaymentpolicy",
            values_callable=lambda enum_cls: [e.value for e in enum_cls],
        ),
        nullable=False,
        default=DividendPaymentPolicy.BANK,
    )

    # The cooperative's own identity, editable from the Settings screen.
    # Defaults mirror the values the frontend shipped with, so a fresh row
    # looks like the product did before branding became configurable.
    cooperative_name = Column(
        String(120), nullable=False, default=DEFAULT_COOPERATIVE_NAME
    )
    cooperative_short_name = Column(
        String(32), nullable=False, default=DEFAULT_COOPERATIVE_SHORT_NAME
    )
    cooperative_monogram = Column(
        String(8), nullable=False, default=DEFAULT_COOPERATIVE_MONOGRAM
    )
    # Uploaded logo (Vercel Blob). The public URL is all we need: replacing
    # or removing it deletes the blob by that same URL.
    logo_url = Column(String(500), nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# ---------------------------------------------------------------------------
# Member savings ledger
#
# Member savings is a liability the cooperative owes the member, so it is
# kept as its own append-only subledger rather than a sign on a shared
# cash list: every entry names what happened, and the balance is the sum
# of the entries. Nothing is ever updated or deleted -- a confirmed payroll
# month that is later voided gets a reversal entry, which is why the
# deduction line link is unique per entry kind.
# ---------------------------------------------------------------------------

class SavingsEntryType(str, enum.Enum):
    CONTRIBUTION = "contribution"
    CONTRIBUTION_REVERSAL = "contribution_reversal"
    # Savings applied to the member's loans when they leave the
    # cooperative, and the balance returned to them in cash.
    EXIT_OFFSET = "exit_offset"
    EXIT_PAYOUT = "exit_payout"


class SavingsEntry(Base):
    __tablename__ = "savings_entries"
    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_savings_entries_amount_positive"),
        UniqueConstraint(
            "deduction_line_id",
            "entry_type",
            name="uq_savings_entries_line_kind",
        ),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    member_id = Column(
        UUID(as_uuid=True), ForeignKey("members.id", ondelete="CASCADE"), nullable=False
    )

    entry_type = Column(
        Enum(SavingsEntryType, values_callable=lambda enum_cls: [e.value for e in enum_cls]),
        nullable=False,
    )
    amount = Column(Numeric(14, 2), nullable=False)

    # The payroll line that produced a contribution (or its reversal).
    deduction_line_id = Column(
        UUID(as_uuid=True),
        ForeignKey("payroll_deduction_lines.id", ondelete="CASCADE"),
        nullable=True,
    )
    settlement_id = Column(
        UUID(as_uuid=True),
        ForeignKey("member_settlements.id", ondelete="CASCADE"),
        nullable=True,
    )

    posted_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    posted_at = Column(DateTime, default=datetime.utcnow)
    note = Column(Text, nullable=True)


class SettlementPayoutStatus(str, enum.Enum):
    PENDING = "pending"
    PAID = "paid"


class SettlementPaymentMethod(str, enum.Enum):
    CASH = "cash"
    BANK = "bank"


class MemberSettlement(Base):
    """
    One member's exit settlement: their savings first offset their active
    loans (oldest loan first), and whatever remains is paid out to them.

    The figures are snapshots of the moment of settlement, not derived
    later -- a payroll correction cannot rewrite what the office settled.
    The ledger is debited in full at settlement; marking the payout paid
    records that the office handed the money over, and the cashbook posts
    the matching journal entry for each step.
    """

    __tablename__ = "member_settlements"
    __table_args__ = (
        CheckConstraint("savings_balance >= 0", name="ck_member_settlements_savings_nonnegative"),
        CheckConstraint("offset_total >= 0", name="ck_member_settlements_offset_nonnegative"),
        CheckConstraint("payout_amount >= 0", name="ck_member_settlements_payout_nonnegative"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    member_id = Column(
        UUID(as_uuid=True),
        ForeignKey("members.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )

    settled_on = Column(Date, nullable=False)
    settled_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    settled_at = Column(DateTime, default=datetime.utcnow)

    savings_balance = Column(Numeric(14, 2), nullable=False)
    offset_total = Column(Numeric(14, 2), nullable=False)
    payout_amount = Column(Numeric(14, 2), nullable=False)

    payout_status = Column(
        Enum(SettlementPayoutStatus, values_callable=lambda enum_cls: [e.value for e in enum_cls]),
        nullable=False,
        default=SettlementPayoutStatus.PENDING,
    )
    paid_on = Column(Date, nullable=True)
    paid_at = Column(DateTime, nullable=True)
    paid_reference = Column(String, nullable=True)
    paid_from = Column(
        Enum(
            SettlementPaymentMethod,
            values_callable=lambda enum_cls: [e.value for e in enum_cls],
        ),
        nullable=True,
    )
    note = Column(Text, nullable=True)

    member = relationship("Member")
    allocations = relationship(
        "SettlementAllocation",
        back_populates="settlement",
        cascade="all, delete-orphan",
        order_by="SettlementAllocation.created_at",
    )


class SettlementAllocation(Base):
    """How much of one settlement went to one loan."""

    __tablename__ = "settlement_allocations"
    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_settlement_allocations_amount_positive"),
        UniqueConstraint("settlement_id", "loan_id", name="uq_settlement_allocations_loan"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    settlement_id = Column(
        UUID(as_uuid=True), ForeignKey("member_settlements.id", ondelete="CASCADE"), nullable=False
    )
    loan_id = Column(UUID(as_uuid=True), ForeignKey("loans.id"), nullable=False)
    amount = Column(Numeric(14, 2), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    settlement = relationship("MemberSettlement", back_populates="allocations")
    loan = relationship("Loan")

    @property
    def loan_type_name(self) -> Optional[str]:
        """Exposed so the settlement breakdown can say which loan the
        offset went to without the client fetching each loan."""
        return self.loan.loan_type.name if self.loan and self.loan.loan_type else None


class CashbookAccountKind(str, enum.Enum):
    ASSET = "asset"
    LIABILITY = "liability"
    EQUITY = "equity"
    INCOME = "income"
    EXPENSE = "expense"


class CashbookEntrySource(str, enum.Enum):
    """What produced the entry. ``source_id`` points at the originating row
    so a re-run can never post the same event twice."""

    MANUAL = "manual"
    OPENING = "opening"
    REVERSAL = "reversal"
    PAYROLL_DEDUCTION = "payroll_deduction"
    PAYROLL_DEDUCTION_VOID = "payroll_deduction_void"
    LOAN_DISBURSEMENT = "loan_disbursement"
    LOAN_REPAYMENT = "loan_repayment"
    LOAN_FEE = "loan_fee"
    SETTLEMENT = "settlement"
    SETTLEMENT_PAYOUT = "settlement_payout"
    YEAR_CLOSE = "year_close"
    DIVIDEND_DECLARATION = "dividend_declaration"
    DIVIDEND_PAYMENT = "dividend_payment"


class CashbookAccount(Base):
    """One line of the chart of accounts.

    ``kind`` decides everything the workbook decided from the sign of an
    amount: whether a balance sits on the balance sheet or in the surplus,
    and on which side. ``system_key`` marks the accounts the automatic
    postings target (bank, cash, member savings, ...); those are protected
    from deactivation because a posting rule names them.
    """

    __tablename__ = "cashbook_accounts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    code = Column(String(16), nullable=False, unique=True)
    name = Column(String(120), nullable=False)
    kind = Column(
        Enum(CashbookAccountKind, values_callable=lambda enum_cls: [e.value for e in enum_cls]),
        nullable=False,
    )
    system_key = Column(String(40), nullable=True, unique=True)
    is_active = Column(Boolean, nullable=False, default=True)
    description = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class CashbookEntry(Base):
    """A balanced journal entry. Posted entries are immutable; a mistake is
    corrected with a reversing entry that names the original."""

    __tablename__ = "cashbook_entries"
    __table_args__ = (
        Index(
            "uq_cashbook_entries_source",
            "source",
            "source_id",
            unique=True,
            postgresql_where=text("source_id IS NOT NULL"),
        ),
        Index("ix_cashbook_entries_entry_date", "entry_date"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    entry_date = Column(Date, nullable=False)
    narration = Column(String(255), nullable=False)
    reference = Column(String(64), nullable=True)

    source = Column(
        Enum(CashbookEntrySource, values_callable=lambda enum_cls: [e.value for e in enum_cls]),
        nullable=False,
        default=CashbookEntrySource.MANUAL,
    )
    source_id = Column(UUID(as_uuid=True), nullable=True)

    reverses_entry_id = Column(
        UUID(as_uuid=True), ForeignKey("cashbook_entries.id"), nullable=True
    )
    reversal_reason = Column(Text, nullable=True)

    posted_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    posted_at = Column(DateTime, default=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow)

    lines = relationship(
        "CashbookLine",
        back_populates="entry",
        cascade="all, delete-orphan",
        order_by="CashbookLine.created_at",
    )
    reverses = relationship("CashbookEntry", remote_side=[id], uselist=False)


class CashbookLine(Base):
    """One side of a journal entry: exactly one of debit/credit is set."""

    __tablename__ = "cashbook_lines"
    __table_args__ = (
        CheckConstraint(
            "(debit > 0 AND credit = 0) OR (credit > 0 AND debit = 0)",
            name="ck_cashbook_lines_one_side",
        ),
        Index("ix_cashbook_lines_account_id", "account_id"),
        Index("ix_cashbook_lines_entry_id", "entry_id"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    entry_id = Column(
        UUID(as_uuid=True), ForeignKey("cashbook_entries.id", ondelete="CASCADE"), nullable=False
    )
    account_id = Column(UUID(as_uuid=True), ForeignKey("cashbook_accounts.id"), nullable=False)
    debit = Column(Numeric(14, 2), nullable=False, default=0)
    credit = Column(Numeric(14, 2), nullable=False, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)

    entry = relationship("CashbookEntry", back_populates="lines")
    account = relationship("CashbookAccount")


class CashbookPeriodLock(Base):
    """A closed month. Entries dated inside it are refused; corrections
    land in the open month as reversing entries."""

    __tablename__ = "cashbook_period_locks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    period_start = Column(Date, nullable=False, unique=True)
    locked_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    locked_at = Column(DateTime, default=datetime.utcnow)
    note = Column(Text, nullable=True)


# ---------------------------------------------------------------------------
# Dividends
#
# A declared dividend is an appropriation of surplus already earned, never
# an expense: the year is closed into retained earnings, then the pool,
# reserve and honorarium are credited out of it. A run snapshots every
# policy figure and every member's basis at declaration time, so a later
# settings change can never rewrite a declared dividend.
# ---------------------------------------------------------------------------

class DividendRun(Base):
    __tablename__ = "dividend_runs"
    __table_args__ = (
        CheckConstraint("period_start <= period_end", name="ck_dividend_runs_no_self_period"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    fiscal_year = Column(Integer, nullable=False, unique=True)
    period_start = Column(Date, nullable=False)
    period_end = Column(Date, nullable=False)
    status = Column(
        Enum(DividendRunStatus, name="dividendrunstatus", values_callable=lambda enum_cls: [e.value for e in enum_cls]),
        nullable=False,
        default=DividendRunStatus.DRAFT,
    )
    basis = Column(
        Enum(DividendBasis, name="dividendbasis", values_callable=lambda enum_cls: [e.value for e in enum_cls]),
        nullable=False,
    )
    pool_mode = Column(
        Enum(
            DividendPoolMode,
            name="dividendpoolmode",
            values_callable=lambda enum_cls: [e.value for e in enum_cls],
        ),
        nullable=False,
    )

    surplus = Column(Numeric(14, 2), nullable=False, default=0)
    reserve_pct = Column(Numeric(5, 2), nullable=False, default=0)
    reserve_amount = Column(Numeric(14, 2), nullable=False, default=0)
    honorarium_pct = Column(Numeric(5, 2), nullable=False, default=0)
    honorarium_amount = Column(Numeric(14, 2), nullable=False, default=0)
    payout_pct = Column(Numeric(5, 2), nullable=False, default=0)
    pool_amount = Column(Numeric(14, 2), nullable=False, default=0)
    declared_rate_pct = Column(Numeric(5, 2), nullable=True)
    fixed_pool_amount = Column(Numeric(14, 2), nullable=True)
    hybrid_savings_pct = Column(Numeric(5, 2), nullable=False, default=50)
    withholding_pct = Column(Numeric(5, 2), nullable=False, default=0)
    rounding = Column(
        Enum(
            DividendRounding,
            name="dividendrounding",
            values_callable=lambda enum_cls: [e.value for e in enum_cls],
        ),
        nullable=False,
        default=DividendRounding.TWO_DP,
    )
    min_membership_months = Column(Integer, nullable=False, default=0)
    include_exited = Column(Boolean, nullable=False, default=False)

    closed_income_total = Column(Numeric(14, 2), nullable=False, default=0)
    closed_expense_total = Column(Numeric(14, 2), nullable=False, default=0)
    total_basis_amount = Column(Numeric(18, 6), nullable=False, default=0)
    total_gross = Column(Numeric(14, 2), nullable=False, default=0)
    total_withholding = Column(Numeric(14, 2), nullable=False, default=0)
    total_net = Column(Numeric(14, 2), nullable=False, default=0)
    rounding_residual = Column(Numeric(14, 2), nullable=False, default=0)
    eligible_member_count = Column(Integer, nullable=False, default=0)

    note = Column(Text, nullable=True)
    declared_on = Column(Date, nullable=True)
    declared_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    created_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    allocations = relationship(
        "DividendAllocation",
        back_populates="run",
        cascade="all, delete-orphan",
        order_by="DividendAllocation.created_at",
    )
    payouts = relationship(
        "DividendPayout",
        back_populates="run",
        cascade="all, delete-orphan",
        order_by="DividendPayout.paid_on",
    )


class DividendPayout(Base):
    """One payment batch. The cashbook entry is keyed to this row, so the
    same batch can never leave the bank twice."""

    __tablename__ = "dividend_payouts"
    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_dividend_payouts_amount_positive"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id = Column(
        UUID(as_uuid=True), ForeignKey("dividend_runs.id", ondelete="CASCADE"), nullable=False
    )
    paid_on = Column(Date, nullable=False)
    method = Column(
        Enum(
            DividendPayoutMethod,
            name="dividendpayoutmethod",
            values_callable=lambda enum_cls: [e.value for e in enum_cls],
        ),
        nullable=False,
    )
    reference = Column(String(64), nullable=False)
    amount = Column(Numeric(14, 2), nullable=False)
    note = Column(Text, nullable=True)
    created_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    run = relationship("DividendRun", back_populates="payouts")
    allocations = relationship("DividendAllocation", back_populates="payout")


class DividendAllocation(Base):
    __tablename__ = "dividend_allocations"
    __table_args__ = (
        UniqueConstraint("run_id", "member_id", name="uq_dividend_allocations_member"),
        CheckConstraint(
            "basis_amount >= 0 AND gross_amount >= 0"
            " AND withholding_amount >= 0 AND net_amount >= 0",
            name="ck_dividend_allocations_amounts_nonnegative",
        ),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id = Column(
        UUID(as_uuid=True), ForeignKey("dividend_runs.id", ondelete="CASCADE"), nullable=False
    )
    member_id = Column(
        UUID(as_uuid=True), ForeignKey("members.id", ondelete="CASCADE"), nullable=False
    )
    # Money bases store naira; the hybrid basis stores a dimensionless
    # weighted score, so six decimals rather than two.
    basis_amount = Column(Numeric(18, 6), nullable=False, default=0)
    share_ratio = Column(Numeric(18, 12), nullable=False, default=0)
    gross_amount = Column(Numeric(14, 2), nullable=False, default=0)
    withholding_amount = Column(Numeric(14, 2), nullable=False, default=0)
    net_amount = Column(Numeric(14, 2), nullable=False, default=0)
    rounding_adjustment = Column(Numeric(14, 2), nullable=False, default=0)
    payout_id = Column(
        UUID(as_uuid=True), ForeignKey("dividend_payouts.id", ondelete="SET NULL"), nullable=True
    )
    created_at = Column(DateTime, default=datetime.utcnow)

    run = relationship("DividendRun", back_populates="allocations")
    member = relationship("Member")
    payout = relationship("DividendPayout", back_populates="allocations")
