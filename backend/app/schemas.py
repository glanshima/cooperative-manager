import uuid
from datetime import datetime, date
from decimal import Decimal
from typing import Optional, List

from pydantic import BaseModel, ConfigDict, field_validator

from .models import (
    MemberStatus,
    Gender,
    LoanStatus,
    UserRole,
    LoanApplicationStatus,
    PaymentVerificationStatus,
    LoanRestrictionBehavior,
    RepaymentVerificationStatus,
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

    _validate_psn = field_validator("psn")(validation.validate_psn)
    _validate_email = field_validator("email")(validation.validate_email_format)
    _validate_noke = field_validator("next_of_kin_email")(validation.validate_email_format)
    _validate_phone = field_validator("phone")(validation.validate_phone_format)
    _validate_nokp = field_validator("next_of_kin_phone")(validation.validate_phone_format)


class MemberCreate(MemberBase):
    pass


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

    _validate_email = field_validator("email")(validation.validate_email_format)
    _validate_noke = field_validator("next_of_kin_email")(validation.validate_email_format)
    _validate_phone = field_validator("phone")(validation.validate_phone_format)
    _validate_nokp = field_validator("next_of_kin_phone")(validation.validate_phone_format)


class MemberLoginStatusUpdate(BaseModel):
    """Login State Reconciliation Addendum: deactivate or reactivate an
    EXISTING member self-service login. Does not create or delete the
    User row -- see routers/auth.py:create-member-login for creation,
    and members.py's delete_member docstring (Change-Control C-2) for
    why the User/Member rows themselves are never destroyed here."""

    account_status: AccountStatus
    reason: Optional[str] = None


class MemberOut(MemberBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    created_at: datetime
    updated_at: datetime

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


class RoleCreate(RoleBase):
    permission_codes: List[str] = []


class RoleUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None
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
    payment_reference: str
    receipt_image_base64: str
    receipt_content_type: str

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
    amount_claimed: Decimal
    payment_reference: str
    receipt_content_type: str
    status: RepaymentVerificationStatus
    rejection_reason: Optional[str] = None
    verified_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class LoanRepaymentOutWithReceipt(LoanRepaymentOut):
    receipt_image_base64: str


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
