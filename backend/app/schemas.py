import uuid
from datetime import datetime, date
from decimal import Decimal
from typing import Optional, List

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .models import (
    MemberStatus,
    Gender,
    LoanStatus,
    UserRole,
    LoanApplicationStatus,
    PaymentVerificationStatus,
    LoanRestrictionBehavior,
    RepaymentVerificationStatus,
    ContributionChangeRequestStatus,
    PayrollDeductionStatus,
    PayrollDeductionLineCategory,
    DeductionWorklistEntryState,
    AccountStatus,
)
from . import validation


class MemberBase(BaseModel):
    psn: str
    name: str
    bank_name: Optional[str] = None
    account_number: Optional[str] = None
    gender: Optional[Gender] = None
    department: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    next_of_kin: Optional[str] = None
    next_of_kin_phone: Optional[str] = None
    next_of_kin_address: Optional[str] = None
    next_of_kin_email: Optional[str] = None
    next_of_kin_relationship: Optional[str] = None
    status: MemberStatus = MemberStatus.FINANCIAL
    loan_restricted: bool = False
    restriction_reason: Optional[str] = None

    # The agreed monthly contribution payroll deducts (minimum 5000). An
    # officer records it once, while it is still unset; every later change
    # goes through a ContributionChangeRequest so the deducted figure is
    # never edited silently -- see routers/members.py.
    monthly_contribution_amount: Optional[Decimal] = None

    _validate_psn = field_validator("psn")(validation.validate_psn)
    _validate_email = field_validator("email")(validation.validate_email_format)
    _validate_noke = field_validator("next_of_kin_email")(validation.validate_email_format)
    _validate_phone = field_validator("phone")(validation.validate_phone_format)
    _validate_nokp = field_validator("next_of_kin_phone")(validation.validate_phone_format)
    _validate_contribution = field_validator("monthly_contribution_amount")(
        validation.validate_contribution_amount_optional
    )


class MemberCreate(MemberBase):
    """
    Member Relationship / Next-of-Kin Controlled Remediation (2026-09),
    Section 1: Member creation must explicitly ask "is this member's
    Next of Kin also a cooperative member?" rather than silently
    leaving that unknown -- next_of_kin_is_member is therefore a
    REQUIRED field here (no default), not optional. This deliberately
    breaks any caller of POST /api/members that doesn't yet send it
    (see the Phase 1 report's remediation section for the one
    pre-existing test payload that needed updating) -- an intentional,
    explicit-choice-over-silent-default trade-off the remediation
    prompt calls for ("Do not allow silently allowing an unknown/null
    state unless existing business requirements technically require
    it"), not an oversight.

    When next_of_kin_is_member is True, next_of_kin_member_id is
    required and the existing free-text next_of_kin* fields (inherited
    from MemberBase) are expected to be left unset -- the authoritative
    Next-of-Kin identity then comes from the linked Member record, not
    from duplicated free text (see MemberRelationship's docstring,
    "SELF-REFERENCE" aside: duplicating identity data would let the two
    silently drift out of sync). When False, next_of_kin_member_id must
    be omitted/null, and the pre-existing free-text fields are used
    exactly as before this remediation.
    """

    next_of_kin_is_member: bool
    next_of_kin_member_id: Optional[uuid.UUID] = None

    @model_validator(mode="after")
    def _validate_next_of_kin_choice(self):
        if self.next_of_kin_is_member and self.next_of_kin_member_id is None:
            raise ValueError(
                "next_of_kin_member_id is required when next_of_kin_is_member is true"
            )
        if not self.next_of_kin_is_member and self.next_of_kin_member_id is not None:
            raise ValueError(
                "next_of_kin_member_id must not be set when next_of_kin_is_member is false"
            )
        return self


class MemberUpdate(BaseModel):
    name: Optional[str] = None
    bank_name: Optional[str] = None
    account_number: Optional[str] = None
    gender: Optional[Gender] = None
    department: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    next_of_kin: Optional[str] = None
    next_of_kin_phone: Optional[str] = None
    next_of_kin_address: Optional[str] = None
    next_of_kin_email: Optional[str] = None
    next_of_kin_relationship: Optional[str] = None
    status: Optional[MemberStatus] = None
    loan_restricted: Optional[bool] = None
    restriction_reason: Optional[str] = None

    # Bootstrap only: routers/members.py rejects this once the member has
    # an amount on file, because a change to an agreed contribution needs
    # a second officer's approval (ContributionChangeRequest).
    monthly_contribution_amount: Optional[Decimal] = None

    _validate_contribution = field_validator("monthly_contribution_amount")(
        validation.validate_contribution_amount_optional
    )

    # Member Relationship / Next-of-Kin Controlled Remediation, Section
    # 8 (changing an existing Next-of-Kin relationship): unlike
    # MemberCreate, both fields are OPTIONAL here -- omitting
    # next_of_kin_is_member entirely means "don't touch the Next-of-Kin
    # relationship at all" (the vast majority of member edits have
    # nothing to do with Next of Kin), which is different from
    # explicitly sending next_of_kin_is_member=false (which means
    # "clear/replace with a non-member Next of Kin"). routers/members.py
    # distinguishes these via `"next_of_kin_is_member" in
    # payload.model_dump(exclude_unset=True)`, not by whether the value
    # is truthy.
    next_of_kin_is_member: Optional[bool] = None
    next_of_kin_member_id: Optional[uuid.UUID] = None

    _validate_email = field_validator("email")(validation.validate_email_format)
    _validate_noke = field_validator("next_of_kin_email")(validation.validate_email_format)
    _validate_phone = field_validator("phone")(validation.validate_phone_format)
    _validate_nokp = field_validator("next_of_kin_phone")(validation.validate_phone_format)

    @model_validator(mode="after")
    def _validate_next_of_kin_choice(self):
        if self.next_of_kin_is_member is True and self.next_of_kin_member_id is None:
            raise ValueError(
                "next_of_kin_member_id is required when next_of_kin_is_member is true"
            )
        if self.next_of_kin_is_member is False and self.next_of_kin_member_id is not None:
            raise ValueError(
                "next_of_kin_member_id must not be set when next_of_kin_is_member is false"
            )
        return self


class MemberLoginStatusUpdate(BaseModel):
    """Login State Reconciliation Addendum: deactivate or reactivate an
    EXISTING member self-service login. Does not create or delete the
    User row -- see routers/auth.py:create-member-login for creation,
    and members.py's delete_member docstring (Change-Control C-2) for
    why the User/Member rows themselves are never destroyed here."""

    account_status: AccountStatus
    reason: Optional[str] = None


class MemberWithdrawRequest(BaseModel):
    """Record a membership exit. `reason` is mandatory because the exit
    note is the only explanation a later auditor gets for why a member
    stopped being deducted contributions."""

    reason: str
    exit_date: Optional[date] = None

    @field_validator("reason")
    @classmethod
    def _require_reason(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("A reason is required")
        return value


class NextOfKinMemberSummary(BaseModel):
    """Minimal, display-only projection of a linked Next-of-Kin Member --
    deliberately NOT the full MemberOut (a member editing/viewing
    another member's record as "just the NOK" has no business reason to
    see that person's bank/account/loan-restriction fields). Populated
    live from the Member table at read time (see
    routers/members.py's _attach_next_of_kin), never persisted/cached,
    so it can never go stale relative to the linked Member's own
    record."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    psn: str
    name: str
    phone: Optional[str] = None


class MemberOut(MemberBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    created_at: datetime
    updated_at: datetime

    membership_exit_date: Optional[date] = None
    membership_exit_reason: Optional[str] = None

    # Server-set: the first payroll month monthly_contribution_amount
    # applies to. Bootstrap records it from the current month; an approved
    # change request moves it to a future month, never backwards.
    contribution_effective_from: Optional[date] = None

    # Login State Reconciliation Addendum (2026-08-29): the Members table
    # needs to know whether a login already exists for this member and,
    # if so, whether it's currently active -- computed authoritatively by
    # the backend (list_members/get_member populate these via a join
    # against users.member_id filtered to role='member', never inferred
    # by the frontend from partial data). None/None means no login exists
    # yet ("Create Login" is the correct action); a non-null
    # login_account_status means one does, and the frontend should offer
    # Deactivate/Reactivate instead, never Create.
    login_user_id: Optional[uuid.UUID] = None
    login_account_status: Optional[AccountStatus] = None

    # Member Relationship / Next-of-Kin Controlled Remediation (2026-09):
    # computed, request-scoped fields populated by
    # routers/members.py's _attach_next_of_kin -- never persisted
    # columns on Member itself (see MemberRelationship's docstring for
    # why this is a first-class relationship table, not a
    # next_of_kin_member_id FK on Member). next_of_kin_is_member is None
    # for a legacy record that has never had this question answered
    # (predates this remediation and was NOT auto-converted -- see the
    # Phase 1 report's "Existing Data" finding); True/False otherwise.
    # next_of_kin_member is only ever populated when
    # next_of_kin_is_member is True.
    next_of_kin_is_member: Optional[bool] = None
    next_of_kin_member: Optional[NextOfKinMemberSummary] = None

    # Conflict-of-interest read policy: this row belongs to a member the
    # caller is linked to by an active conflict-flagged relationship. The
    # read is permitted; only ACTIONS are blocked -- see
    # self_conflict.require_no_member_conflict and the write endpoints.
    conflicted: bool = False


class MemberListResponse(BaseModel):
    """Members Search & Filtering Remediation: GET /api/members returns
    this wrapper (not a bare list) specifically so pagination metadata
    (total match count against the FULL filtered dataset, not just the
    current page) is available -- required by that remediation's
    acceptance criteria. This is a deliberate, scoped deviation from the
    flat-list convention used by every other list endpoint in this
    codebase (loans, loan-applications, audit) -- see the Phase 1 report
    for why it wasn't applied everywhere."""

    items: List[MemberOut]
    total: int
    skip: int
    limit: int


class MemberSavingsOut(BaseModel):
    """A member's own accumulated contributions, for their dashboard.

    Kept out of MemberOut deliberately: savings_balance is a SUM over
    confirmed deduction lines, and MemberOut is serialized for every row of
    the members list, where that aggregate would be paid 100 times per page
    to serve nobody who reads it."""

    member_id: uuid.UUID
    savings_balance: Decimal
    months_contributed: int


class MemberWithdrawalOut(BaseModel):
    """What a membership exit means financially, in one response: the
    savings the member takes with them, what they still owe, and how much
    of that has to keep coming out of payroll after the savings offset.

    It reports the offset rather than posting it -- there is no savings
    ledger to move money from, and the repayment flow is the audited
    place money changes hands."""

    member: MemberOut
    savings_balance: Decimal
    active_loan_count: int
    active_loan_outstanding: Decimal
    payroll_recovery_still_due: Decimal


class MemberFilterOptions(BaseModel):
    """Distinct bank_name/department values actually present across
    authorized members right now -- used to populate the Members
    table's filter dropdowns from real data, never fabricated. No
    separate Bank/Department entity exists in this codebase (bank_name
    and department are free-text columns on Member); see the Phase 1
    report for that finding."""

    banks: List[str]
    departments: List[str]


# ---------------------------------------------------------------------------
# Loan Types
# ---------------------------------------------------------------------------

class LoanTypeBase(BaseModel):
    name: str
    description: Optional[str] = None
    is_active: bool = True
    open_for_application: bool = False


class LoanTypeCreate(LoanTypeBase):
    """interest_rate/tenure_months/flat_charge here seed the loan type's
    FIRST rate version. effective_from defaults to today if not given."""
    interest_rate: Decimal
    tenure_months: int
    flat_charge: Decimal = Decimal("0")
    effective_from: Optional[date] = None


class LoanTypeUpdate(BaseModel):
    """Only non-rate fields. To change interest_rate/tenure_months/
    flat_charge, create a new rate version instead (POST
    /api/loan-types/{id}/rate-versions) -- see LoanTypeRateVersionCreate."""
    name: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None
    open_for_application: Optional[bool] = None


class LoanTypeOut(LoanTypeBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    interest_rate: Decimal  # current effective rate (denormalized cache)
    tenure_months: int
    flat_charge: Decimal
    created_at: datetime
    updated_at: datetime


class LoanTypeRateVersionCreate(BaseModel):
    interest_rate: Decimal
    tenure_months: int
    flat_charge: Decimal = Decimal("0")
    effective_from: date


class LoanTypeRateVersionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    loan_type_id: uuid.UUID
    interest_rate: Decimal
    tenure_months: int
    flat_charge: Decimal
    effective_from: date
    created_at: datetime


# ---------------------------------------------------------------------------
# Loans
# ---------------------------------------------------------------------------

class LoanCreate(BaseModel):
    member_id: uuid.UUID
    loan_type_id: uuid.UUID
    principal: Decimal
    disbursement_date: date
    notes: Optional[str] = None

    _validate_principal = field_validator("principal")(validation.validate_positive_amount)


class LoanUpdate(BaseModel):
    amount_repaid: Optional[Decimal] = None
    status: Optional[LoanStatus] = None
    notes: Optional[str] = None


class LoanOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    member_id: uuid.UUID
    loan_type_id: uuid.UUID
    principal: Decimal
    interest_amount: Decimal
    net_disbursed: Decimal
    total_repayable: Decimal
    monthly_installment: Decimal
    disbursement_date: date
    expected_end_date: date
    disbursement_bank_name: Optional[str] = None
    disbursement_account_name: Optional[str] = None
    disbursement_account_number: Optional[str] = None
    amount_repaid: Decimal
    status: LoanStatus
    notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    # True when the caller is conflicted against this loan's member --
    # visible, but every action on it is refused. See MemberOut.conflicted.
    conflicted: bool = False


class LoanOutWithDetails(LoanOut):
    """Includes denormalized member name and loan type name for list views,
    avoiding N+1 lookups on the frontend."""
    member_name: str
    member_psn: str
    loan_type_name: str
    balance: Decimal  # total_repayable - amount_repaid


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

class LoginRequest(BaseModel):
    username: str  # PSN for members, chosen username/email for admins
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: UserRole
    must_change_password: bool


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


class CreateMemberLoginRequest(BaseModel):
    """Admin-only: provisions a login for an existing member."""
    member_id: uuid.UUID
    temporary_password: str


class ForgotPasswordRequest(BaseModel):
    """Initiates self-service password recovery."""
    identifier: str  # PSN, username, or registered email


class VerifyResetTokenRequest(BaseModel):
    """Checks whether a recovery token is valid without consuming it."""
    token: str


class ResetPasswordRequest(BaseModel):
    """Consumes a valid recovery token to set a new password."""
    token: str
    new_password: str


class GenericMessageResponse(BaseModel):
    message: str


class AdminUserPasswordResetRequest(BaseModel):
    """Admin-only: resets a staff/admin account's password with a temporary password."""
    temporary_password: str


class CreateAdminRequest(BaseModel):
    """Used only by the one-off seed script, not exposed over the API."""
    username: str
    password: str


class AdminUserMemberLinkUpdate(BaseModel):
    """Controlled Phase 1 Remediation, Section 10: explicit, manual
    linking of an admin account to the Member record it belongs to (for
    an elected EXCO officer who is also a cooperative member). Set
    member_id to null to clear an existing link."""

    member_id: Optional[uuid.UUID] = None
    reason: Optional[str] = None


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    username: str
    role: UserRole
    member_id: Optional[uuid.UUID] = None
    must_change_password: bool
    is_active: bool
    account_status: AccountStatus
    is_super_admin: bool
    last_login_at: Optional[datetime] = None
    created_at: datetime


# ---------------------------------------------------------------------------
# Office / Role / Permission / Audit (Phase 1)
# ---------------------------------------------------------------------------


class OfficeBase(BaseModel):
    name: str
    description: Optional[str] = None
    is_active: bool = True


class OfficeCreate(OfficeBase):
    pass


class OfficeUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None


class OfficeOut(OfficeBase):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    created_at: datetime


class PermissionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    code: str
    category: str
    description: str


class RoleBase(BaseModel):
    name: str
    description: Optional[str] = None
    is_active: bool = True
    requires_member_link: bool = False


class RoleCreate(RoleBase):
    permission_codes: List[str] = []


class RoleUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None
    requires_member_link: Optional[bool] = None
    permission_codes: Optional[List[str]] = None


class RoleOut(RoleBase):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    created_at: datetime
    permission_codes: List[str] = []


class UserRoleAssignmentCreate(BaseModel):
    user_id: uuid.UUID
    role_id: uuid.UUID
    office_id: Optional[uuid.UUID] = None


class UserRoleAssignmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    user_id: uuid.UUID
    role_id: uuid.UUID
    role_name: str
    office_id: Optional[uuid.UUID] = None
    office_name: Optional[str] = None
    is_active: bool
    assigned_at: datetime
    revoked_at: Optional[datetime] = None


class AdminUserCreate(BaseModel):
    """Creates a new staff/admin User account (distinct from
    create-member-login, which provisions a login for an existing
    Member). New admin accounts start with is_super_admin=False and no
    role assignments -- an authorized admin.role_manage holder must
    grant a role for the account to be able to do anything."""
    username: str
    password: str
    account_status: AccountStatus = AccountStatus.ACTIVE


class AdminUserStatusUpdate(BaseModel):
    account_status: AccountStatus
    reason: Optional[str] = None


class AuditEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    actor_user_id: Optional[uuid.UUID] = None
    actor_username: Optional[str] = None
    actor_office_name: Optional[str] = None
    actor_role_names: Optional[str] = None
    event_type: str
    entity_type: Optional[str] = None
    entity_id: Optional[str] = None
    action: str
    previous_values: Optional[dict] = None
    new_values: Optional[dict] = None
    reason: Optional[str] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    timestamp: datetime


# ---------------------------------------------------------------------------
# Loan Applications
# ---------------------------------------------------------------------------

class LoanApplicationCreate(BaseModel):
    """Submitted by a member. Payment proof is required in the same
    request, since submission is gated on having already paid the fee."""
    loan_type_id: uuid.UUID
    requested_amount: Decimal
    requested_tenure_months: Optional[int] = None  # must be <= the loan type's default tenure
    preferred_disbursement_date: Optional[date] = None  # preference only, not binding
    use_default_account: bool = True
    alternate_bank_name: Optional[str] = None  # required if use_default_account=False
    alternate_account_name: Optional[str] = None  # required if use_default_account=False
    alternate_account_number: Optional[str] = None  # required if use_default_account=False
    member_notes: Optional[str] = None
    payment_reference: str
    receipt_image_base64: str
    receipt_content_type: str
    reapplied_from_id: Optional[uuid.UUID] = None  # set when submitted via the reapply flow

    _validate_amount = field_validator("requested_amount")(validation.validate_positive_amount)
    _validate_receipt_type = field_validator("receipt_content_type")(validation.validate_receipt_content_type)
    _validate_receipt_b64 = field_validator("receipt_image_base64")(validation.validate_receipt_base64)


class PaymentVerificationRequest(BaseModel):
    approved: bool
    rejection_reason: Optional[str] = None  # required by the router if approved=False


class LoanDecisionRequest(BaseModel):
    approved: bool
    approved_amount: Optional[Decimal] = None  # required by the router if approved=True
    approved_tenure_months: Optional[int] = None  # required by the router if approved=True
    tenure_decision_reason: Optional[str] = None  # explain if this differs from what was requested
    admin_notes: Optional[str] = None
    can_reapply: bool = True  # only meaningful when approved=False; admin flips to False for non-qualification


class RescheduleRequest(BaseModel):
    preferred_disbursement_date: date


class DisburseRequest(BaseModel):
    """Optional balance-deduction selection at disbursement time (see
    Round 2 design note): the admin either picks specific active loans
    of this member to fully close out against the new disbursement, or
    sets deduct_all_active=True to close out every active loan. Deducted
    loans always close out completely -- no partial deduction. Leave
    both empty/false for a normal disbursement with no offset."""
    deduct_loan_ids: Optional[List[uuid.UUID]] = None
    deduct_all_active: bool = False


class LoanApplicationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    member_id: uuid.UUID
    loan_type_id: uuid.UUID
    requested_amount: Decimal
    approved_amount: Optional[Decimal] = None
    requested_tenure_months: Optional[int] = None
    approved_tenure_months: Optional[int] = None
    tenure_decision_reason: Optional[str] = None
    preferred_disbursement_date: Optional[date] = None
    use_default_account: bool
    alternate_bank_name: Optional[str] = None
    alternate_account_name: Optional[str] = None
    alternate_account_number: Optional[str] = None
    status: LoanApplicationStatus
    member_notes: Optional[str] = None
    admin_notes: Optional[str] = None
    was_restricted_at_submission: bool
    restriction_reason_snapshot: Optional[str] = None
    form_fee_amount: Decimal
    payment_reference: str
    receipt_content_type: str
    payment_status: PaymentVerificationStatus
    payment_verified_at: Optional[datetime] = None
    payment_rejection_reason: Optional[str] = None
    reviewed_at: Optional[datetime] = None
    resulting_loan_id: Optional[uuid.UUID] = None
    cancelled_at: Optional[datetime] = None
    can_reapply: bool
    reapplied_from_id: Optional[uuid.UUID] = None
    created_at: datetime
    updated_at: datetime

    # True when the caller is conflicted against this application's member.
    conflicted: bool = False


class LoanApplicationOutWithDetails(LoanApplicationOut):
    member_name: str
    member_psn: str
    loan_type_name: str


class LoanApplicationOutWithReceipt(LoanApplicationOutWithDetails):
    """Only returned on the single-application detail view, not list
    views, so the (potentially large) base64 receipt isn't sent on every
    list load."""
    receipt_image_base64: str


class ReapplyRequest(BaseModel):
    """Submitted by a member to create a fresh application from a
    rejected one. A brand new payment is always required -- reapplying
    does not reuse the old (already-consumed) payment proof."""
    requested_amount: Optional[Decimal] = None  # defaults to the original's amount if omitted
    requested_tenure_months: Optional[int] = None
    preferred_disbursement_date: Optional[date] = None
    use_default_account: bool = True
    alternate_bank_name: Optional[str] = None
    alternate_account_name: Optional[str] = None
    alternate_account_number: Optional[str] = None
    member_notes: Optional[str] = None
    payment_reference: str
    receipt_image_base64: str
    receipt_content_type: str

    _validate_amount = field_validator("requested_amount")(validation.validate_positive_amount_optional)
    _validate_receipt_type = field_validator("receipt_content_type")(validation.validate_receipt_content_type)
    _validate_receipt_b64 = field_validator("receipt_image_base64")(validation.validate_receipt_base64)


# ---------------------------------------------------------------------------
# Loan Repayments
# ---------------------------------------------------------------------------

class LoanRepaymentCreate(BaseModel):
    amount_claimed: Decimal
    # The payroll month this payment belongs to, not the submission date: a
    # member paying by bank transfer must not also be charged that instalment
    # through payroll for the same month.
    payment_month: str
    payment_reference: str
    receipt_image_base64: str
    receipt_content_type: str

    _validate_month = field_validator("payment_month")(validation.validate_month)
    _validate_amount = field_validator("amount_claimed")(validation.validate_positive_amount)
    _validate_receipt_type = field_validator("receipt_content_type")(validation.validate_receipt_content_type)
    _validate_receipt_b64 = field_validator("receipt_image_base64")(validation.validate_receipt_base64)


class RepaymentVerificationRequest(BaseModel):
    approved: bool
    rejection_reason: Optional[str] = None  # required by the router if approved=False


class LoanRepaymentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    loan_id: uuid.UUID
    member_id: uuid.UUID
    # None on records created before the month was captured; the payroll
    # prefill surfaces those instead of guessing a month.
    payment_month: Optional[date] = None
    amount_claimed: Decimal
    payment_reference: str
    receipt_content_type: str
    status: RepaymentVerificationStatus
    rejection_reason: Optional[str] = None
    verified_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    # True when the caller is conflicted against this repayment's member.
    conflicted: bool = False


class LoanRepaymentOutWithReceipt(LoanRepaymentOut):
    receipt_image_base64: str


# ---------------------------------------------------------------------------
# Monthly contribution changes
# ---------------------------------------------------------------------------

def _required_reason(value: str) -> str:
    value = value.strip()
    if not value:
        raise ValueError("A reason is required")
    return value


class ContributionChangeRequestCreate(BaseModel):
    """A member's own application to change their monthly contribution.
    There is no member_id here: the self-service endpoint always applies to
    the caller's own record."""

    requested_amount: Decimal
    reason: str

    _validate_amount = field_validator("requested_amount")(validation.validate_contribution_amount)
    _validate_reason = field_validator("reason")(_required_reason)


class ContributionChangeRequestOnBehalf(ContributionChangeRequestCreate):
    """The same application raised by an officer, for a member who has no
    login of their own to apply with."""

    member_id: uuid.UUID


class ContributionChangeReviewRequest(BaseModel):
    # Required when rejecting, optional when approving -- the router decides.
    reason: Optional[str] = None


class ContributionChangeRequestOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    member_id: uuid.UUID
    member_name: Optional[str] = None
    member_psn: Optional[str] = None

    # Snapshot of what the member was paying when they applied, so the
    # review screen still shows the move after approval overwrites it.
    current_amount: Optional[Decimal] = None
    requested_amount: Decimal
    reason: Optional[str] = None

    status: ContributionChangeRequestStatus
    effective_from: Optional[date] = None

    requested_by_user_id: Optional[uuid.UUID] = None
    reviewed_by_user_id: Optional[uuid.UUID] = None
    reviewed_at: Optional[datetime] = None
    review_reason: Optional[str] = None

    created_at: datetime
    updated_at: datetime

    # Conflict-of-interest read policy: the request stays visible and
    # flagged; deciding it is what stays blocked.
    conflicted: bool = False


# ---------------------------------------------------------------------------
# Payroll Deductions
# ---------------------------------------------------------------------------

class PayrollDeductionLineInput(BaseModel):
    category: PayrollDeductionLineCategory
    loan_id: Optional[uuid.UUID] = None
    label: Optional[str] = None
    amount: Decimal

    _validate_amount = field_validator("amount")(validation.validate_positive_amount)

    @field_validator("label")
    @classmethod
    def _strip_label(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        value = value.strip()
        return value or None

    @model_validator(mode="after")
    def _validate_category_shape(self):
        if self.category in (
            PayrollDeductionLineCategory.LOAN_REPAYMENT,
            PayrollDeductionLineCategory.LOAN_ARREARS,
        ):
            if self.loan_id is None:
                raise ValueError(f"A {self.category.value} line requires loan_id")
        else:
            if self.loan_id is not None:
                raise ValueError(
                    "Only loan_repayment or loan_arrears lines may reference a loan"
                )
            if self.category == PayrollDeductionLineCategory.OTHER and not self.label:
                raise ValueError("An 'other' deduction requires a label")
        return self


def _validate_line_set(lines: List[PayrollDeductionLineInput]) -> List[PayrollDeductionLineInput]:
    if not lines:
        raise ValueError("At least one deduction line is required")
    # One loan can legitimately appear twice -- this month's instalment and a
    # catch-up of earlier ones -- so uniqueness is per loan AND category.
    loan_slots = [(line.loan_id, line.category) for line in lines if line.loan_id is not None]
    if len(loan_slots) != len(set(loan_slots)):
        raise ValueError(
            "A loan may have at most one repayment line and one arrears line "
            "in a monthly deduction"
        )
    contributions = [
        line for line in lines if line.category == PayrollDeductionLineCategory.MONTHLY_CONTRIBUTION
    ]
    if len(contributions) > 1:
        raise ValueError("A monthly deduction can only have one contribution line")
    return lines


class PayrollDeductionCreate(BaseModel):
    member_id: uuid.UUID
    deduction_month: str
    payroll_reference: Optional[str] = None
    note: Optional[str] = None
    lines: List[PayrollDeductionLineInput]

    _validate_month = field_validator("deduction_month")(validation.validate_month)
    _validate_lines = field_validator("lines")(_validate_line_set)


class PayrollDeductionUpdate(BaseModel):
    """Draft-only edit. Omitted fields are left unchanged; sending `lines`
    replaces the whole set (lines are a single unit, not individually
    editable)."""

    deduction_month: Optional[str] = None
    payroll_reference: Optional[str] = None
    note: Optional[str] = None
    lines: Optional[List[PayrollDeductionLineInput]] = None

    _validate_month = field_validator("deduction_month")(validation.validate_month)
    _validate_line_set = field_validator("lines")(_validate_line_set)


class PayrollDeductionReasonRequest(BaseModel):
    reason: str

    @field_validator("reason")
    @classmethod
    def _require_reason(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("A reason is required")
        return value


class PayrollDeductionBulkRequest(BaseModel):
    # Bounded on purpose: every record in a batch commits on its own (the
    # audit write inside the bulk loop commits), so a request that outlives
    # the deployment's function timeout would leave a half-applied batch and
    # no per-item report. Callers chunk larger selections instead.
    ids: List[uuid.UUID] = Field(max_length=100)
    reason: Optional[str] = None

    @field_validator("ids")
    @classmethod
    def _require_ids(cls, value: List[uuid.UUID]) -> List[uuid.UUID]:
        if not value:
            raise ValueError("At least one deduction id is required")
        return value


class PayrollDeductionLineOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    category: PayrollDeductionLineCategory
    loan_id: Optional[uuid.UUID] = None
    label: Optional[str] = None
    amount: Decimal
    # Server-derived expectation for this line's month; None when nothing
    # on file predicts it. amount != expected_amount is an override.
    expected_amount: Optional[Decimal] = None
    loan_type_name: Optional[str] = None


class PayrollDeductionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    member_id: uuid.UUID
    member_name: Optional[str] = None
    member_psn: Optional[str] = None
    deduction_month: date
    payroll_reference: Optional[str] = None
    note: Optional[str] = None
    status: PayrollDeductionStatus

    contribution_total: Decimal
    loan_total: Decimal
    arrears_total: Decimal
    other_total: Decimal
    grand_total: Decimal

    submitted_at: Optional[datetime] = None
    confirmed_at: Optional[datetime] = None
    not_deducted_at: Optional[datetime] = None
    not_deducted_reason: Optional[str] = None
    returned_at: Optional[datetime] = None
    return_reason: Optional[str] = None
    voided_at: Optional[datetime] = None
    void_reason: Optional[str] = None

    created_at: datetime
    updated_at: datetime

    # True when the caller is conflicted against this record's member --
    # the schedule and ledger stay complete, the buttons go quiet.
    conflicted: bool = False

    lines: List[PayrollDeductionLineOut] = Field(default_factory=list)


class PayrollDeductionListResponse(BaseModel):
    """The ledger is paginated so a month's worth of records doesn't render
    as one endless scroll. Mirrors MemberListResponse: the wrapper exists so
    `total` counts the FULL filtered dataset, not the current page."""

    items: List[PayrollDeductionOut]
    total: int
    skip: int
    limit: int


class PayrollDeductionSubmittableIds(BaseModel):
    """Scope for "submit all drafts". Drafts with no lines are reported
    separately instead of arriving as bulk failures -- an officer should see
    "left as drafts" rather than an error for expected incompleteness."""

    month: date
    ids: List[uuid.UUID]
    empty_draft_ids: List[uuid.UUID]


class PayrollDeductionTotals(BaseModel):
    contribution_total: Decimal
    loan_total: Decimal
    arrears_total: Decimal
    other_total: Decimal
    grand_total: Decimal


class PayrollDeductionScheduleOut(BaseModel):
    month: date
    records: List[PayrollDeductionOut]
    totals: PayrollDeductionTotals


class DeductionWorklistLine(BaseModel):
    category: PayrollDeductionLineCategory
    amount: Decimal
    loan_id: Optional[uuid.UUID] = None
    loan_type_name: Optional[str] = None
    # The loan's past-due position, computed rather than stored: what the
    # schedule should already have collected. Arrears get their own line, so
    # the catch-up is entered as a decision instead of silently accumulated;
    # both of a loan's lines carry the figures so either reads on its own.
    arrears: Decimal
    months_behind: int


class DeductionWorklistItem(BaseModel):
    member_id: uuid.UUID
    member_name: str
    member_psn: str
    member_status: MemberStatus
    membership_exit_date: Optional[date] = None
    due_reasons: List[str]
    lines: List[DeductionWorklistLine]
    warnings: List[str]
    expected_total: Decimal
    # Set when the month already has a live record for this member
    # (entry_state=entered or all).
    deduction_id: Optional[uuid.UUID] = None
    deduction_status: Optional[PayrollDeductionStatus] = None
    conflicted: bool = False


class DeductionWorklistOut(BaseModel):
    """The queue is paginated like the ledger (see
    PayrollDeductionListResponse), but the three month-wide counts and
    `expected_total` deliberately are NOT page-scoped: an officer deciding
    how much of the month is left needs the whole month's picture while
    looking at one page of it.

    `pending_count` + `entered_count` == `due_count`, so the segment tabs can
    show their true sizes whatever page is open. A live record for a member
    nothing currently expects (a loan repaid since, a member who exited) is
    not in `entered_count` -- the ledger is the complete record list."""

    month: date
    items: List[DeductionWorklistItem]
    total: int
    skip: int
    limit: int
    entry_state: DeductionWorklistEntryState
    due_count: int
    pending_count: int
    entered_count: int
    # What is still outstanding: members already entered for the month are
    # counted in entered_count, not added here.
    expected_total: Decimal


class PayrollDeductionBulkResult(BaseModel):
    id: uuid.UUID
    ok: bool
    status: Optional[PayrollDeductionStatus] = None
    detail: Optional[str] = None


class PayrollDeductionBulkResponse(BaseModel):
    results: List[PayrollDeductionBulkResult]


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

class SettingsOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    loan_restriction_behavior: LoanRestrictionBehavior
    loan_form_fee: Decimal
    members_module_enabled: bool
    loans_module_enabled: bool
    deductions_module_enabled: bool
    cashbook_module_enabled: bool
    dividends_module_enabled: bool


class SettingsUpdate(BaseModel):
    loan_restriction_behavior: Optional[LoanRestrictionBehavior] = None
    loan_form_fee: Optional[Decimal] = None
    members_module_enabled: Optional[bool] = None
    loans_module_enabled: Optional[bool] = None
    deductions_module_enabled: Optional[bool] = None
    cashbook_module_enabled: Optional[bool] = None
    dividends_module_enabled: Optional[bool] = None
