"""
Authoritative Phase 1 permission catalogue (spec Section 9), plus a small
set of default roles used only to seed a usable starting point -- roles
and their permission grants remain ordinary, admin-editable configuration
data after seeding (see routers/roles.py), not hard-coded logic.

Every permission code referenced anywhere in the backend (deps.py's
require_permission calls) MUST appear in PERMISSION_CATALOGUE. This is
enforced by scripts/seed_permissions.py failing loudly on drift, and by
tests/test_permission_catalogue.py.

CONTROLLED IMPLEMENTATION -- Admin Governance & Member-Link Enforcement
(2026-08), Section 3: the 4th element of each tuple below is
`requires_member_link` -- whether *holding this permission* is
sensitive enough that an admin account must be linked to a Member
(User.member_id) -- or explicitly confirmed as a legitimate non-member
account (User.confirmed_non_member_admin, see models.py) -- before it
can be granted. This is a plain, code-defined classification (not
admin-editable), same trust level as the catalogue itself, seeded onto
`Permission.requires_member_link` by scripts/seed_permissions.py.

Classified as requiring a member link: any permission that can approve,
disburse, verify, or otherwise decide a financial outcome for a member,
or post/alter the accounting ledger. Deliberately NOT classified as
sensitive: pure viewing/reporting, record maintenance that isn't a
financial decision (member.create/update, disbursement.prepare -- staging
only, not a decision), and Administration/Audit permissions, which
govern the system itself rather than deciding a member's money.
"""

# (code, category, description, requires_member_link)
PERMISSION_CATALOGUE = [
    # Members
    ("member.view", "Members", "View member records", False),
    ("member.create", "Members", "Create a new member record", False),
    ("member.update", "Members", "Edit an existing member record", False),
    ("member.deactivate", "Members", "Deactivate or reactivate a member record", False),
    # Savings (foundation only -- full savings engine is Phase 4)
    ("savings.view", "Savings", "View savings/contribution records", False),
    ("savings.request_change", "Savings", "Request a savings amount change", False),
    ("savings.approve_change", "Savings", "Approve a savings amount change request", True),
    ("savings.reject_change", "Savings", "Reject a savings amount change request", True),
    # Loans
    ("loan.view", "Loans", "View loans and loan applications", False),
    ("loan.review", "Loans", "Verify loan-application form-fee payments", True),
    ("loan.approve", "Loans", "Approve or reject a loan application decision", True),
    ("loan.reject", "Loans", "Reject a loan application decision", True),
    # Disbursement
    ("disbursement.prepare", "Disbursement", "Prepare a disbursement/manifest", False),
    ("disbursement.approve", "Disbursement", "Approve a prepared disbursement", True),
    ("disbursement.submit", "Disbursement", "Submit/execute a disbursement", True),
    ("disbursement.reconcile", "Disbursement", "Reconcile a disbursement against bank confirmation", True),
    # Repayments
    ("repayment.view", "Repayments", "View loan repayments", False),
    ("repayment.record", "Repayments", "Record a repayment", False),
    ("repayment.verify", "Repayments", "Verify/reject a submitted repayment", True),
    ("repayment.reverse", "Repayments", "Reverse a previously verified repayment", True),
    # Accounting foundation (full ledger is Phase 3)
    ("accounting.view", "Accounting", "View accounting records", False),
    ("accounting.post", "Accounting", "Post an accounting transaction", True),
    ("accounting.adjust", "Accounting", "Adjust an accounting transaction", True),
    ("accounting.reverse", "Accounting", "Reverse an accounting transaction", True),
    ("accounting.reconcile", "Accounting", "Reconcile accounting records", True),
    # Reports
    ("report.member", "Reports", "Run member-level reports", False),
    ("report.financial", "Reports", "Run financial reports", False),
    ("report.accounting", "Reports", "Run accounting reports", False),
    ("report.export", "Reports", "Export a report", False),
    # Administration
    ("admin.user_manage", "Administration", "Create, update, suspend or deactivate user accounts", False),
    ("admin.role_manage", "Administration", "Create, update and assign roles", False),
    ("admin.permission_manage", "Administration", "View permissions and manage role-permission grants", False),
    ("admin.office_manage", "Administration", "Create and update offices/positions", False),
    ("admin.settings_manage", "Administration", "Edit cooperative-wide settings", False),
    # Audit
    ("audit.view", "Audit", "View the audit trail", False),
    ("audit.export", "Audit", "Export audit events", False),
]

PERMISSION_CODES = {code for code, _, _, _ in PERMISSION_CATALOGUE}
SENSITIVE_FINANCIAL_PERMISSION_CODES = {
    code for code, _, _, requires_member_link in PERMISSION_CATALOGUE if requires_member_link
}

# Default roles seeded on first setup. These are a *starting point*, not a
# lock-in -- an authorized admin (admin.role_manage) can rename, retire, or
# create additional roles, and can change which permissions any role
# grants, through the roles API.
DEFAULT_ROLES = {
    "Super Admin": {
        "description": "Full configuration authority. Reserved for a small number of accounts.",
        "permissions": sorted(PERMISSION_CODES),
    },
    "Loan Officer": {
        "description": "Reviews and decides loan applications; verifies repayments.",
        "permissions": [
            "member.view",
            "loan.view",
            "loan.review",
            "loan.approve",
            "loan.reject",
            "repayment.view",
            "repayment.verify",
            "report.member",
        ],
    },
    "Treasurer": {
        "description": "Handles disbursement and financial reconciliation.",
        "permissions": [
            "member.view",
            "loan.view",
            "disbursement.prepare",
            "disbursement.approve",
            "disbursement.submit",
            "disbursement.reconcile",
            "accounting.view",
            "accounting.post",
            "accounting.reconcile",
            "report.financial",
            "report.accounting",
        ],
    },
    "Secretary": {
        "description": "Maintains member records and savings-change decisions.",
        "permissions": [
            "member.view",
            "member.create",
            "member.update",
            "savings.view",
            "savings.approve_change",
            "savings.reject_change",
            "report.member",
        ],
    },
    "Auditor": {
        "description": "Read-only oversight of financial records and the audit trail.",
        "permissions": [
            "member.view",
            "loan.view",
            "repayment.view",
            "accounting.view",
            "report.financial",
            "report.accounting",
            "audit.view",
            "audit.export",
        ],
    },
}
