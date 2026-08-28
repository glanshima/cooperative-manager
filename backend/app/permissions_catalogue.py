"""
Authoritative Phase 1 permission catalogue (spec Section 9), plus a small
set of default roles used only to seed a usable starting point -- roles
and their permission grants remain ordinary, admin-editable configuration
data after seeding (see routers/roles.py), not hard-coded logic.

Every permission code referenced anywhere in the backend (deps.py's
require_permission calls) MUST appear in PERMISSION_CATALOGUE. This is
enforced by scripts/seed_permissions.py failing loudly on drift, and by
tests/test_permission_catalogue.py.
"""

# (code, category, description)
PERMISSION_CATALOGUE = [
    # Members
    ("member.view", "Members", "View member records"),
    ("member.create", "Members", "Create a new member record"),
    ("member.update", "Members", "Edit an existing member record"),
    ("member.deactivate", "Members", "Deactivate or reactivate a member record"),
    # Savings (foundation only -- full savings engine is Phase 4)
    ("savings.view", "Savings", "View savings/contribution records"),
    ("savings.request_change", "Savings", "Request a savings amount change"),
    ("savings.approve_change", "Savings", "Approve a savings amount change request"),
    ("savings.reject_change", "Savings", "Reject a savings amount change request"),
    # Loans
    ("loan.view", "Loans", "View loans and loan applications"),
    ("loan.review", "Loans", "Verify loan-application form-fee payments"),
    ("loan.approve", "Loans", "Approve or reject a loan application decision"),
    ("loan.reject", "Loans", "Reject a loan application decision"),
    # Disbursement
    ("disbursement.prepare", "Disbursement", "Prepare a disbursement/manifest"),
    ("disbursement.approve", "Disbursement", "Approve a prepared disbursement"),
    ("disbursement.submit", "Disbursement", "Submit/execute a disbursement"),
    ("disbursement.reconcile", "Disbursement", "Reconcile a disbursement against bank confirmation"),
    # Repayments
    ("repayment.view", "Repayments", "View loan repayments"),
    ("repayment.record", "Repayments", "Record a repayment"),
    ("repayment.verify", "Repayments", "Verify/reject a submitted repayment"),
    ("repayment.reverse", "Repayments", "Reverse a previously verified repayment"),
    # Accounting foundation (full ledger is Phase 3)
    ("accounting.view", "Accounting", "View accounting records"),
    ("accounting.post", "Accounting", "Post an accounting transaction"),
    ("accounting.adjust", "Accounting", "Adjust an accounting transaction"),
    ("accounting.reverse", "Accounting", "Reverse an accounting transaction"),
    ("accounting.reconcile", "Accounting", "Reconcile accounting records"),
    # Reports
    ("report.member", "Reports", "Run member-level reports"),
    ("report.financial", "Reports", "Run financial reports"),
    ("report.accounting", "Reports", "Run accounting reports"),
    ("report.export", "Reports", "Export a report"),
    # Administration
    ("admin.user_manage", "Administration", "Create, update, suspend or deactivate user accounts"),
    ("admin.role_manage", "Administration", "Create, update and assign roles"),
    ("admin.permission_manage", "Administration", "View permissions and manage role-permission grants"),
    ("admin.office_manage", "Administration", "Create and update offices/positions"),
    ("admin.settings_manage", "Administration", "Edit cooperative-wide settings"),
    # Audit
    ("audit.view", "Audit", "View the audit trail"),
    ("audit.export", "Audit", "Export audit events"),
]

PERMISSION_CODES = {code for code, _, _ in PERMISSION_CATALOGUE}

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
