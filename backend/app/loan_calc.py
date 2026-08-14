"""
Shared loan-terms calculation, mirroring the original workbook's IFS-based
formulas, kept in one place so direct admin disbursement and
application-approval disbursement can never drift out of sync.

Interest-at-source model (confirmed with MACT): interest is deducted from
what's actually paid out to the member, not added on top of what they
repay. A flat_charge, if any, is a separate processing fee and IS still
added to the repayable amount -- only interest is "at source."
"""

from datetime import date
from decimal import Decimal

from dateutil.relativedelta import relativedelta
from sqlalchemy.orm import Session

from . import models


def compute_loan_terms(principal: Decimal, interest_rate: Decimal, flat_charge: Decimal, tenure_months: int):
    """
    interest_amount     = principal * rate
    net_disbursed         = principal - interest_amount   (what the member actually receives)
    total_repayable        = principal + flat_charge        (interest is NOT added back in)
    monthly_installment    = total_repayable / tenure_months
    """
    interest_amount = principal * interest_rate
    net_disbursed = principal - interest_amount
    total_repayable = principal + flat_charge
    monthly_installment = total_repayable / tenure_months
    return interest_amount, net_disbursed, total_repayable, monthly_installment


def compute_expected_end_date(disbursement_date: date, tenure_months: int) -> date:
    """EDATE(disbursement_date, tenure_months) equivalent."""
    return disbursement_date + relativedelta(months=tenure_months)


def get_effective_rate_version(db: Session, loan_type_id, as_of_date: date):
    """
    Returns whichever rate version was effective on the given date (the
    most recent version with effective_from <= as_of_date). Returns None
    if no version exists that early -- callers should fall back to the
    loan_type's own denormalized fields in that edge case (shouldn't
    normally happen once every loan type has at least one version, which
    creation/migration always ensures).
    """
    return (
        db.query(models.LoanTypeRateVersion)
        .filter(
            models.LoanTypeRateVersion.loan_type_id == loan_type_id,
            models.LoanTypeRateVersion.effective_from <= as_of_date,
        )
        .order_by(models.LoanTypeRateVersion.effective_from.desc())
        .first()
    )


def get_effective_terms(db: Session, loan_type, as_of_date: date):
    """
    Returns (interest_rate, tenure_months, flat_charge) effective as of
    the given date for this loan type, falling back to the loan type's
    own cached fields if somehow no version row exists yet.
    """
    version = get_effective_rate_version(db, loan_type.id, as_of_date)
    if version:
        return version.interest_rate, version.tenure_months, version.flat_charge
    return loan_type.interest_rate, loan_type.tenure_months, loan_type.flat_charge


def sync_loan_type_cache(db: Session, loan_type):
    """
    After creating a new rate version, refresh LoanType's denormalized
    interest_rate/tenure_months/flat_charge to match whichever version is
    effective today -- so code reading those fields directly (the admin
    list view, the application form's "default tenure" display) shows
    the current rate without needing date-aware queries. Does nothing if
    the newest applicable version is unchanged (e.g. a future-dated
    version was added but hasn't taken effect yet).
    """
    current = get_effective_rate_version(db, loan_type.id, date.today())
    if current:
        loan_type.interest_rate = current.interest_rate
        loan_type.tenure_months = current.tenure_months
        loan_type.flat_charge = current.flat_charge
