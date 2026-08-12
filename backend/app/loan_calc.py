"""
Shared loan-terms calculation, mirroring the original workbook's IFS-based
formulas. Kept in one place so direct admin disbursement (routers/loans.py)
and application-approval disbursement (routers/loan_applications.py) can
never drift out of sync with each other.
"""

from datetime import date
from decimal import Decimal

from dateutil.relativedelta import relativedelta


def compute_loan_terms(principal: Decimal, interest_rate: Decimal, flat_charge: Decimal, tenure_months: int):
    """
    interest_amount      = principal * rate
    total_repayable       = principal + interest_amount + flat_charge
    monthly_installment   = total_repayable / tenure_months
    """
    interest_amount = principal * interest_rate
    total_repayable = principal + interest_amount + flat_charge
    monthly_installment = total_repayable / tenure_months
    return interest_amount, total_repayable, monthly_installment


def compute_expected_end_date(disbursement_date: date, tenure_months: int) -> date:
    """EDATE(disbursement_date, tenure_months) equivalent."""
    return disbursement_date + relativedelta(months=tenure_months)
