"""Aggregates for the admin landing dashboard.

Every figure is computed on request from the same tables the module pages
read -- nothing is cached or stored, so the dashboard cannot drift from
the authoritative records. A section is returned as ``None`` when the
caller lacks the permission for it (or its module is switched off); the
router never exposes a value it would not expose on the module page.
"""
import uuid
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Dict, List, Optional, Set

from sqlalchemy import case, func
from sqlalchemy.orm import Session

from . import cashbook, models

ZERO = Decimal("0")
CENT = Decimal("0.01")

PERIOD_KEYS = ("this_month", "last_month", "this_year", "last_year")
PERIOD_LABELS = {
    "this_month": "This month",
    "last_month": "Last month",
    "this_year": "This year",
    "last_year": "Last year",
}

CASH_SYSTEM_KEYS = ("CASH", "BANK")
TREND_MONTHS = 6
ACTIVITY_LIMIT = 8


def _money(value) -> Decimal:
    return Decimal(value or 0).quantize(CENT)


def _month_start(day: date) -> date:
    return day.replace(day=1)


def _add_months(day: date, months: int) -> date:
    total = day.year * 12 + (day.month - 1) + months
    return date(total // 12, total % 12 + 1, 1)


def _fiscal_start(today: date, start_month: int) -> date:
    year = today.year if today.month >= start_month else today.year - 1
    return date(year, start_month, 1)


def resolve_period(key: str, today: date, fiscal_start_month: int):
    """The reporting window for one preset. Movement metrics sum rows whose
    own date falls inside it; snapshot metrics ignore it."""
    if key == "this_month":
        start, end = _month_start(today), today
    elif key == "last_month":
        end = _month_start(today) - timedelta(days=1)
        start = _month_start(end)
    elif key == "this_year":
        start, end = _fiscal_start(today, fiscal_start_month), today
    elif key == "last_year":
        current = _fiscal_start(today, fiscal_start_month)
        end = current - timedelta(days=1)
        start = date(current.year - 1, fiscal_start_month, 1)
    else:  # pragma: no cover - the router constrains the parameter
        raise ValueError(f"Unknown dashboard period {key!r}")
    return start, end


def _day_bounds(start: date, end: date):
    """[start 00:00, end+1 00:00) for naive datetime columns."""
    return datetime.combine(start, time.min), datetime.combine(end + timedelta(days=1), time.min)


def _members(db: Session, start: date, end: date) -> dict:
    rows = (
        db.query(models.Member.status, func.count(models.Member.id))
        .group_by(models.Member.status)
        .all()
    )
    counts = {status: count for status, count in rows}
    exited = (
        db.query(func.count(models.Member.id))
        .filter(models.Member.membership_exit_date.isnot(None))
        .scalar()
    )
    joined_from, joined_to = _day_bounds(start, end)
    joined = (
        db.query(func.count(models.Member.id))
        .filter(models.Member.created_at >= joined_from, models.Member.created_at < joined_to)
        .scalar()
    )
    return {
        "total": sum(counts.values()),
        "financial": counts.get(models.MemberStatus.FINANCIAL, 0),
        "non_financial": counts.get(models.MemberStatus.NON_FINANCIAL, 0),
        "exited": exited or 0,
        "joined": joined or 0,
    }


def _savings(db: Session, start: date, end: date) -> dict:
    rows = (
        db.query(
            models.SavingsEntry.entry_type,
            func.coalesce(func.sum(models.SavingsEntry.amount), 0),
        )
        .group_by(models.SavingsEntry.entry_type)
        .all()
    )
    credits = ZERO
    debits = ZERO
    for entry_type, total in rows:
        if entry_type == models.SavingsEntryType.CONTRIBUTION:
            credits += Decimal(total or 0)
        else:
            debits += Decimal(total or 0)

    posted_from, posted_to = _day_bounds(start, end)
    collected = (
        db.query(func.coalesce(func.sum(models.SavingsEntry.amount), 0))
        .filter(
            models.SavingsEntry.entry_type == models.SavingsEntryType.CONTRIBUTION,
            models.SavingsEntry.posted_at >= posted_from,
            models.SavingsEntry.posted_at < posted_to,
        )
        .scalar()
    )
    paid_out = (
        db.query(func.coalesce(func.sum(models.SavingsEntry.amount), 0))
        .filter(
            models.SavingsEntry.entry_type == models.SavingsEntryType.EXIT_PAYOUT,
            models.SavingsEntry.posted_at >= posted_from,
            models.SavingsEntry.posted_at < posted_to,
        )
        .scalar()
    )
    return {
        "total": _money(credits - debits),
        "collected": _money(collected),
        "paid_out": _money(paid_out),
    }


def _loans(db: Session, start: date, end: date, permissions: Set[str]) -> dict:
    active_count, outstanding = (
        db.query(
            func.count(models.Loan.id),
            func.coalesce(
                func.sum(models.Loan.total_repayable - models.Loan.amount_repaid), 0
            ),
        )
        .filter(models.Loan.status == models.LoanStatus.ACTIVE)
        .one()
    )
    defaulted = (
        db.query(func.count(models.Loan.id))
        .filter(models.Loan.status == models.LoanStatus.DEFAULTED)
        .scalar()
    )
    disbursed_count, disbursed = (
        db.query(
            func.count(models.Loan.id),
            func.coalesce(func.sum(models.Loan.principal), 0),
        )
        .filter(
            models.Loan.disbursement_date >= start,
            models.Loan.disbursement_date <= end,
        )
        .one()
    )
    section = {
        "active_count": active_count or 0,
        "outstanding": _money(outstanding),
        "defaulted_count": defaulted or 0,
        "disbursed_count": disbursed_count or 0,
        "disbursed": _money(disbursed),
        "repayments": None,
    }
    if "repayment.view" in permissions:
        verified_from, verified_to = _day_bounds(start, end)
        verified_count, verified_amount = (
            db.query(
                func.count(models.LoanRepayment.id),
                func.coalesce(func.sum(models.LoanRepayment.amount_claimed), 0),
            )
            .filter(
                models.LoanRepayment.status
                == models.RepaymentVerificationStatus.VERIFIED,
                models.LoanRepayment.verified_at >= verified_from,
                models.LoanRepayment.verified_at < verified_to,
            )
            .one()
        )
        section["repayments"] = {
            "count": verified_count or 0,
            "amount": _money(verified_amount),
        }
    return section


def _deductions(db: Session, start: date, end: date) -> dict:
    confirmed_total, confirmed_members = (
        db.query(
            func.coalesce(func.sum(models.PayrollDeductionLine.amount), 0),
            func.count(func.distinct(models.PayrollDeduction.member_id)),
        )
        .join(
            models.PayrollDeduction,
            models.PayrollDeduction.id == models.PayrollDeductionLine.deduction_id,
        )
        .filter(
            models.PayrollDeduction.status == models.PayrollDeductionStatus.CONFIRMED,
            models.PayrollDeduction.deduction_month >= _month_start(start),
            models.PayrollDeduction.deduction_month <= end,
        )
        .one()
    )
    drafts = (
        db.query(func.count(models.PayrollDeduction.id))
        .filter(models.PayrollDeduction.status == models.PayrollDeductionStatus.DRAFT)
        .scalar()
    )
    submitted = (
        db.query(func.count(models.PayrollDeduction.id))
        .filter(models.PayrollDeduction.status == models.PayrollDeductionStatus.SUBMITTED)
        .scalar()
    )
    return {
        "confirmed_total": _money(confirmed_total),
        "confirmed_members": confirmed_members or 0,
        "draft_count": drafts or 0,
        "submitted_count": submitted or 0,
    }


def _cashbook(db: Session) -> dict:
    if not cashbook.books_open(db):
        return {"books_open": False, "cash": None, "bank": None, "total": None}
    cash = ZERO
    bank = ZERO
    for row in cashbook.account_balances(db):
        if row.account.system_key not in CASH_SYSTEM_KEYS:
            continue
        net = row.debit - row.credit
        if row.account.system_key == "CASH":
            cash += net
        else:
            bank += net
    return {"books_open": True, "cash": _money(cash), "bank": _money(bank), "total": _money(cash + bank)}


def _dividends(db: Session) -> dict:
    live_statuses = (models.DividendRunStatus.DECLARED, models.DividendRunStatus.PAID)
    last = (
        db.query(models.DividendRun)
        .filter(models.DividendRun.status.in_(live_statuses))
        .order_by(models.DividendRun.fiscal_year.desc())
        .first()
    )
    unpaid, paid = (
        db.query(
            func.coalesce(
                func.sum(
                    case(
                        (models.DividendAllocation.payout_id.is_(None), models.DividendAllocation.net_amount),
                        else_=ZERO,
                    )
                ),
                0,
            ),
            func.coalesce(
                func.sum(
                    case(
                        (models.DividendAllocation.payout_id.isnot(None), models.DividendAllocation.net_amount),
                        else_=ZERO,
                    )
                ),
                0,
            ),
        )
        .join(models.DividendRun, models.DividendRun.id == models.DividendAllocation.run_id)
        .filter(models.DividendRun.status.in_(live_statuses))
        .one()
    )
    return {
        "last_declared_year": last.fiscal_year if last else None,
        "last_declared_on": last.declared_on if last else None,
        "last_pool": _money(last.pool_amount) if last else None,
        "unpaid_net": _money(unpaid),
        "paid_net": _money(paid),
    }


def _queues(db: Session, permissions: Set[str]) -> List[dict]:
    """Work the officer can act on right now, each linking to its queue.
    The count is the authoritative workflow state, not a guess."""
    items: List[dict] = []

    def add(key, label, count, href, amount=None):
        if count:
            items.append(
                {"key": key, "label": label, "count": count, "amount": amount, "href": href}
            )

    if "loan.review" in permissions:
        reviewable = (
            db.query(func.count(models.LoanApplication.id))
            .filter(
                models.LoanApplication.status == models.LoanApplicationStatus.PENDING,
                models.LoanApplication.payment_status
                == models.PaymentVerificationStatus.VERIFIED,
            )
            .scalar()
        )
        add(
            "applications_review",
            "Loan applications awaiting review",
            reviewable or 0,
            "/admin/loan-applications?queue=review",
        )
        payments = (
            db.query(func.count(models.LoanApplication.id))
            .filter(
                models.LoanApplication.payment_status
                == models.PaymentVerificationStatus.AWAITING_VERIFICATION
            )
            .scalar()
        )
        add(
            "application_payments",
            "Application fees awaiting verification",
            payments or 0,
            "/admin/loan-applications?queue=payment",
        )

    if "disbursement.submit" in permissions:
        awaiting = (
            db.query(func.count(models.LoanApplication.id))
            .filter(
                models.LoanApplication.status == models.LoanApplicationStatus.APPROVED,
                models.LoanApplication.resulting_loan_id.is_(None),
            )
            .scalar()
        )
        add(
            "disbursements",
            "Approved loans awaiting disbursement",
            awaiting or 0,
            "/admin/disbursements",
        )

    if "repayment.verify" in permissions:
        pending = (
            db.query(func.count(models.LoanRepayment.id))
            .filter(
                models.LoanRepayment.status
                == models.RepaymentVerificationStatus.AWAITING_VERIFICATION
            )
            .scalar()
        )
        add(
            "repayments",
            "Repayments awaiting verification",
            pending or 0,
            "/admin/loan-repayments?status=awaiting_verification",
        )

    if "loan.fee_verify" in permissions:
        fees = (
            db.query(func.count(models.LoanFeePayment.id))
            .filter(models.LoanFeePayment.status == models.FeePaymentStatus.AWAITING_VERIFICATION)
            .scalar()
        )
        add("loan_fees", "Loan fees awaiting verification", fees or 0, "/admin/loan-fees")

    if "deduction.submit" in permissions:
        drafts = (
            db.query(func.count(models.PayrollDeduction.id))
            .filter(models.PayrollDeduction.status == models.PayrollDeductionStatus.DRAFT)
            .scalar()
        )
        add("deduction_drafts", "Deduction drafts not yet submitted", drafts or 0, "/admin/deductions")

    if "deduction.confirm" in permissions:
        submitted = (
            db.query(func.count(models.PayrollDeduction.id))
            .filter(models.PayrollDeduction.status == models.PayrollDeductionStatus.SUBMITTED)
            .scalar()
        )
        add(
            "deduction_submitted",
            "Deduction schedules awaiting confirmation",
            submitted or 0,
            "/admin/deductions",
        )

    if "savings.settle" in permissions:
        count, amount = (
            db.query(
                func.count(models.MemberSettlement.id),
                func.coalesce(func.sum(models.MemberSettlement.payout_amount), 0),
            )
            .filter(models.MemberSettlement.payout_status == models.SettlementPayoutStatus.PENDING)
            .one()
        )
        add(
            "settlements",
            "Exit settlements awaiting payout",
            count or 0,
            "/members?settlement=pending",
            amount=_money(amount) if count else None,
        )

    if "dividend.pay" in permissions:
        unpaid = (
            db.query(func.count(models.DividendAllocation.id))
            .join(models.DividendRun, models.DividendRun.id == models.DividendAllocation.run_id)
            .filter(
                models.DividendRun.status == models.DividendRunStatus.DECLARED,
                models.DividendAllocation.payout_id.is_(None),
            )
            .scalar()
        )
        add(
            "dividends",
            "Dividend allocations awaiting payout",
            unpaid or 0,
            "/admin/dividends",
        )

    return items


def _activity(db: Session) -> List[dict]:
    rows = (
        db.query(models.AuditEvent)
        .order_by(models.AuditEvent.timestamp.desc())
        .limit(ACTIVITY_LIMIT)
        .all()
    )
    return [
        {
            "event_type": row.event_type,
            "action": row.action,
            "actor": row.actor_username or "System",
            "entity_type": row.entity_type,
            "entity_id": row.entity_id,
            "timestamp": row.timestamp,
        }
        for row in rows
    ]


def _trend(db: Session, today: date, permissions: Set[str]) -> Optional[dict]:
    show_savings = "savings.view" in permissions
    show_repayments = "repayment.view" in permissions
    if not show_savings and not show_repayments:
        return None

    months = [_add_months(_month_start(today), -offset) for offset in range(TREND_MONTHS - 1, -1, -1)]
    first, last_exclusive = months[0], _add_months(months[-1], 1)
    window_start = datetime.combine(first, time.min)
    window_end = datetime.combine(last_exclusive, time.min)
    index = {(month.year, month.month): position for position, month in enumerate(months)}

    savings: Optional[List[Decimal]] = None
    if show_savings:
        savings = [ZERO] * len(months)
        rows = (
            db.query(
                func.date_trunc("month", models.SavingsEntry.posted_at),
                func.coalesce(func.sum(models.SavingsEntry.amount), 0),
            )
            .filter(
                models.SavingsEntry.entry_type == models.SavingsEntryType.CONTRIBUTION,
                models.SavingsEntry.posted_at >= window_start,
                models.SavingsEntry.posted_at < window_end,
            )
            .group_by(func.date_trunc("month", models.SavingsEntry.posted_at))
            .all()
        )
        for bucket, total in rows:
            position = index.get((bucket.year, bucket.month))
            if position is not None:
                savings[position] = _money(total)
        savings = [str(value) for value in savings]

    repayments: Optional[List[Decimal]] = None
    if show_repayments:
        repayments = [ZERO] * len(months)
        rows = (
            db.query(
                func.date_trunc("month", models.LoanRepayment.verified_at),
                func.coalesce(func.sum(models.LoanRepayment.amount_claimed), 0),
            )
            .filter(
                models.LoanRepayment.status == models.RepaymentVerificationStatus.VERIFIED,
                models.LoanRepayment.verified_at >= window_start,
                models.LoanRepayment.verified_at < window_end,
            )
            .group_by(func.date_trunc("month", models.LoanRepayment.verified_at))
            .all()
        )
        for bucket, total in rows:
            position = index.get((bucket.year, bucket.month))
            if position is not None:
                repayments[position] = _money(total)
        repayments = [str(value) for value in repayments]

    return {
        "months": [month.strftime("%Y-%m") for month in months],
        "savings": savings,
        "repayments": repayments,
    }


def build_dashboard(
    db: Session,
    permissions: List[str],
    period_key: str,
    *,
    today: Optional[date] = None,
) -> dict:
    today = today or date.today()
    settings = db.query(models.Settings).first()
    fiscal_month = settings.fiscal_year_start_month if settings else 1
    start, end = resolve_period(period_key, today, fiscal_month)
    perms = set(permissions)

    members_enabled = settings.members_module_enabled if settings else True
    loans_enabled = settings.loans_module_enabled if settings else True
    deductions_enabled = settings.deductions_module_enabled if settings else True
    cashbook_enabled = settings.cashbook_module_enabled if settings else False
    dividends_enabled = settings.dividends_module_enabled if settings else False

    return {
        "period": {
            "key": period_key,
            "label": PERIOD_LABELS[period_key],
            "start": start,
            "end": end,
        },
        "members": _members(db, start, end)
        if members_enabled and "member.view" in perms
        else None,
        "savings": _savings(db, start, end) if "savings.view" in perms else None,
        "loans": _loans(db, start, end, perms)
        if loans_enabled and "loan.view" in perms
        else None,
        "deductions": _deductions(db, start, end)
        if deductions_enabled and "deduction.view" in perms
        else None,
        "cashbook": _cashbook(db)
        if cashbook_enabled and "accounting.view" in perms
        else None,
        "dividends": _dividends(db)
        if dividends_enabled and "dividend.view" in perms
        else None,
        "queues": _queues(db, perms),
        "activity": _activity(db) if "audit.view" in perms else None,
        "trend": _trend(db, today, perms),
    }
