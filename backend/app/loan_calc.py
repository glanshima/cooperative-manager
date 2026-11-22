"""
Shared loan-terms calculation, kept in one place so direct admin
disbursement and application-approval disbursement can never drift out
of sync.

Interest can be recovered three ways (see InterestDeductionMode):

  at_source            interest is deducted from the payout; the member
                       repays the principal.
  spread_over_tenure   the full principal is paid out; interest is
                       repaid in level instalments over the tenure.
  spread_first_months  the full principal is paid out; the monthly
                       instalment carries ``interest / N`` extra during
                       the first N months, then drops to principal only.

The loan type's flat_charge is a processing fee paid separately. It is
never part of the payout, the total repayable or the instalment, so it
does not appear in these calculations at all.
"""

from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import NamedTuple, Optional

from dateutil.relativedelta import relativedelta
from sqlalchemy.orm import Session

from . import models

ZERO = Decimal("0")
CENT = Decimal("0.01")


def _money(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


class LoanTerms(NamedTuple):
    interest_amount: Decimal
    net_disbursed: Decimal
    total_repayable: Decimal
    monthly_installment: Decimal
    # Extra monthly amount during the first interest_spread_months
    # instalments; zero for the other modes.
    interest_installment: Decimal


def compute_loan_terms(
    principal: Decimal,
    interest_rate: Decimal,
    tenure_months: int,
    mode: models.InterestDeductionMode = models.InterestDeductionMode.AT_SOURCE,
    spread_months: Optional[int] = None,
) -> LoanTerms:
    """All figures are money (2 dp). Interest is calculated once from the
    principal and never re-derived, so the mode only decides who pays it
    and when."""
    interest_amount = _money(principal * interest_rate)

    if mode == models.InterestDeductionMode.AT_SOURCE:
        total_repayable = principal
        net_disbursed = principal - interest_amount
        monthly_installment = _money(total_repayable / tenure_months)
        interest_installment = ZERO
    elif mode == models.InterestDeductionMode.SPREAD_OVER_TENURE:
        total_repayable = principal + interest_amount
        net_disbursed = principal
        monthly_installment = _money(total_repayable / tenure_months)
        interest_installment = ZERO
    elif mode == models.InterestDeductionMode.SPREAD_FIRST_MONTHS:
        if not spread_months or spread_months <= 0:
            raise ValueError("spread_months is required for spread_first_months")
        if spread_months > tenure_months:
            raise ValueError("spread_months cannot exceed the tenure")
        total_repayable = principal + interest_amount
        net_disbursed = principal
        monthly_installment = _money(principal / tenure_months)
        interest_installment = _money(interest_amount / spread_months)
    else:
        raise ValueError(f"Unknown interest mode: {mode}")

    return LoanTerms(
        interest_amount=interest_amount,
        net_disbursed=net_disbursed,
        total_repayable=total_repayable,
        monthly_installment=monthly_installment,
        interest_installment=interest_installment,
    )


def instalment_for_due_month(loan: models.Loan, due_months: int) -> Decimal:
    """What this instalment should be, ``due_months`` instalments after
    the first due month (1-based)."""
    if (
        loan.interest_mode == models.InterestDeductionMode.SPREAD_FIRST_MONTHS
        and loan.interest_installment
        and due_months <= (loan.interest_spread_months or 0)
    ):
        return loan.monthly_installment + loan.interest_installment
    return loan.monthly_installment


def expected_total_by_due_month(loan: models.Loan, due_months: int) -> Decimal:
    """Total the schedule should have collected after ``due_months``
    instalments, capped at what the loan actually owes."""
    if loan.interest_mode == models.InterestDeductionMode.SPREAD_FIRST_MONTHS:
        covered = min(due_months, loan.interest_spread_months or 0)
        scheduled = loan.monthly_installment * due_months + loan.interest_installment * covered
    else:
        scheduled = loan.monthly_installment * due_months
    return min(scheduled, loan.total_repayable)


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


def _cooperative_defaults(db: Session):
    settings = db.query(models.Settings).first()
    if settings is None:
        return models.InterestDeductionMode.AT_SOURCE, None
    return settings.loan_interest_mode, settings.loan_interest_spread_months


def resolve_interest_terms(db: Session, loan_type, as_of_date: date):
    """Interest mode and spread months for a new loan disbursed on
    ``as_of_date``: the rate version's override wins, then the loan
    type's cached value, then the cooperative default. Months are only
    meaningful for SPREAD_FIRST_MONTHS and fall back independently."""
    version = get_effective_rate_version(db, loan_type.id, as_of_date)
    source = version if version is not None else loan_type

    default_mode, default_months = _cooperative_defaults(db)
    mode = source.interest_mode or loan_type.interest_mode or default_mode
    months = source.interest_spread_months or loan_type.interest_spread_months or default_months
    return mode, months


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
    interest_rate/tenure_months/flat_charge/interest_mode/
    interest_spread_months to match whichever version is effective today
    -- so code reading those fields directly (the admin list view, the
    application form's "default tenure" display) shows the current terms
    without needing date-aware queries. Does nothing if the newest
    applicable version is unchanged (e.g. a future-dated version was
    added but hasn't taken effect yet).
    """
    current = get_effective_rate_version(db, loan_type.id, date.today())
    if current:
        loan_type.interest_rate = current.interest_rate
        loan_type.tenure_months = current.tenure_months
        loan_type.flat_charge = current.flat_charge
        loan_type.interest_mode = current.interest_mode
        loan_type.interest_spread_months = current.interest_spread_months
