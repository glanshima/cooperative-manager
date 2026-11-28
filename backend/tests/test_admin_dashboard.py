"""Admin dashboard aggregates: permission-gated sections over real rows.

The dashboard stores nothing, so these tests pin the two things that can
go wrong without a schema to protect them:
  - a section must be absent (null), not zeroed, when the caller lacks the
    permission or the module is off;
  - period metrics must respect the selected window while snapshot metrics
    stay as-of-now, and the totals must match the authoritative tables.
"""
from datetime import date, datetime, timedelta
from decimal import Decimal

from app import models
from app.permissions_catalogue import PERMISSION_CATALOGUE
from tests.conftest import (
    auth_headers,
    grant_permission,
    make_admin_user,
    make_loan_type,
    make_member,
    make_settings,
)

ZERO = Decimal("0.00")


def _admin(db_session, *codes):
    existing = {row.code for row in db_session.query(models.Permission.code).all()}
    for code, category, description in PERMISSION_CATALOGUE:
        if code not in existing:
            db_session.add(models.Permission(code=code, category=category, description=description))
    db_session.commit()
    admin = make_admin_user(db_session)
    if codes:
        grant_permission(db_session, admin, *codes)
    return admin


def _dashboard(client, admin, period="this_month"):
    response = client.get(
        f"/api/admin/dashboard?period={period}", headers=auth_headers(admin)
    )
    assert response.status_code == 200, response.text
    return response.json()


def _loan(db_session, member, loan_type, *, principal="1000.00", interest="100.00",
          repaid="0.00", disbursed=None, status=models.LoanStatus.ACTIVE):
    loan = models.Loan(
        member_id=member.id,
        loan_type_id=loan_type.id,
        principal=Decimal(principal),
        interest_amount=Decimal(interest),
        net_disbursed=Decimal(principal),
        total_repayable=Decimal(principal) + Decimal(interest),
        monthly_installment=Decimal("100.00"),
        interest_mode=models.InterestDeductionMode.AT_SOURCE,
        disbursement_date=disbursed or date.today(),
        expected_end_date=date(date.today().year + 1, 1, 1),
        amount_repaid=Decimal(repaid),
        status=status,
    )
    db_session.add(loan)
    db_session.commit()
    db_session.refresh(loan)
    return loan


def _account(db_session, code, name, kind, system_key):
    account = (
        db_session.query(models.CashbookAccount)
        .filter(models.CashbookAccount.code == code)
        .first()
    )
    if account is None:
        account = models.CashbookAccount(code=code, name=name, kind=kind, system_key=system_key)
        db_session.add(account)
        db_session.commit()
    return account


def _contribution(db_session, member, amount, *, kind=models.SavingsEntryType.CONTRIBUTION,
                  posted_at=None):
    entry = models.SavingsEntry(
        member_id=member.id,
        entry_type=kind,
        amount=Decimal(amount),
        posted_at=posted_at or datetime.utcnow(),
    )
    db_session.add(entry)
    db_session.commit()
    return entry


def test_sections_are_null_without_permissions(client, db_session):
    admin = _admin(db_session)  # an admin, but no role grants

    body = _dashboard(client, admin)

    assert body["period"]["key"] == "this_month"
    assert body["period"]["start"] == date.today().replace(day=1).isoformat()
    assert body["period"]["end"] == date.today().isoformat()
    for section in ("members", "savings", "loans", "deductions", "cashbook", "dividends"):
        assert body[section] is None, section
    assert body["queues"] == []
    assert body["activity"] is None
    assert body["trend"] is None


def test_members_counts_and_joined(client, db_session):
    admin = _admin(db_session, "member.view")
    make_member(db_session, psn="PSN-1", email="one@example.com")
    make_member(db_session, psn="PSN-2", email="two@example.com")
    exited = make_member(db_session, psn="PSN-3", email="three@example.com")
    exited.status = models.MemberStatus.NON_FINANCIAL
    exited.membership_exit_date = date.today()
    db_session.commit()

    members = _dashboard(client, admin)["members"]

    assert members["total"] == 3
    assert members["financial"] == 2
    assert members["non_financial"] == 1
    assert members["exited"] == 1
    assert members["joined"] == 3  # all created moments ago, inside this month


def test_savings_total_is_net_of_reversals_and_payouts(client, db_session):
    admin = _admin(db_session, "savings.view")
    first = make_member(db_session, psn="PSN-1", email="one@example.com")
    second = make_member(db_session, psn="PSN-2", email="two@example.com")
    _contribution(db_session, first, "1000.00")
    _contribution(db_session, first, "250.00", kind=models.SavingsEntryType.CONTRIBUTION_REVERSAL)
    _contribution(db_session, second, "100.00", kind=models.SavingsEntryType.EXIT_PAYOUT)

    savings = _dashboard(client, admin)["savings"]

    assert Decimal(savings["total"]) == Decimal("650.00")
    assert Decimal(savings["collected"]) == Decimal("1000.00")
    assert Decimal(savings["paid_out"]) == Decimal("100.00")


def test_loans_outstanding_snapshot_and_disbursement_period(client, db_session):
    admin = _admin(db_session, "loan.view")
    member = make_member(db_session)
    earlier_member = make_member(db_session, psn="PSN-2", email="two@example.com")
    loan_type = make_loan_type(db_session, "Salary Loan")
    _loan(db_session, member, loan_type, principal="1000.00", interest="100.00", repaid="200.00")
    last_month_end = date.today().replace(day=1) - timedelta(days=1)
    _loan(
        db_session, earlier_member, loan_type,
        principal="500.00", interest="50.00", disbursed=last_month_end,
    )

    this_month = _dashboard(client, admin, "this_month")["loans"]
    assert this_month["active_count"] == 2
    # Outstanding uses total_repayable - amount_repaid: (1100-200) + 550.
    assert Decimal(this_month["outstanding"]) == Decimal("1450.00")
    assert this_month["disbursed_count"] == 1
    assert Decimal(this_month["disbursed"]) == Decimal("1000.00")
    assert this_month["repayments"] is None  # no repayment.view

    last_month = _dashboard(client, admin, "last_month")["loans"]
    assert last_month["disbursed_count"] == 1
    assert Decimal(last_month["disbursed"]) == Decimal("500.00")


def test_repayment_totals_need_repayment_view(client, db_session):
    admin = _admin(db_session, "loan.view", "repayment.view")
    member = make_member(db_session)
    loan_type = make_loan_type(db_session, "Salary Loan")
    loan = _loan(db_session, member, loan_type)
    db_session.add(
        models.LoanRepayment(
            loan_id=loan.id,
            member_id=member.id,
            payment_month=date.today().replace(day=1),
            amount_claimed=Decimal("300.00"),
            payment_reference="TRF-1",
            receipt_image_base64="aGVsbG8=",
            receipt_content_type="image/png",
            status=models.RepaymentVerificationStatus.VERIFIED,
            verified_at=datetime.utcnow(),
        )
    )
    db_session.commit()

    repayments = _dashboard(client, admin)["loans"]["repayments"]

    assert repayments["count"] == 1
    assert Decimal(repayments["amount"]) == Decimal("300.00")


def test_cashbook_section_follows_module_and_books_state(client, db_session):
    admin = _admin(db_session, "accounting.view")

    # Module off (the default): the section is absent even with the permission.
    assert _dashboard(client, admin)["cashbook"] is None

    make_settings(db_session, cashbook_module_enabled=True)
    closed = _dashboard(client, admin)["cashbook"]
    assert closed == {"books_open": False, "cash": None, "bank": None, "total": None}

    bank = _account(db_session, "1010", "Bank", models.CashbookAccountKind.ASSET, "BANK")
    equity = _account(
        db_session, "3000", "Retained earnings", models.CashbookAccountKind.EQUITY,
        "RETAINED_EARNINGS",
    )
    entry = models.CashbookEntry(
        entry_date=date.today(),
        narration="Opening balances",
        source=models.CashbookEntrySource.OPENING,
    )
    db_session.add(entry)
    db_session.flush()
    db_session.add_all([
        models.CashbookLine(entry_id=entry.id, account_id=bank.id, debit=Decimal("5000.00"), credit=ZERO),
        models.CashbookLine(entry_id=entry.id, account_id=equity.id, debit=ZERO, credit=Decimal("5000.00")),
    ])
    db_session.commit()

    opened = _dashboard(client, admin)["cashbook"]
    assert opened["books_open"] is True
    assert Decimal(opened["bank"]) == Decimal("5000.00")
    assert Decimal(opened["total"]) == Decimal("5000.00")


def test_dividend_position_reports_unpaid_net(client, db_session):
    admin = _admin(db_session, "dividend.view")
    make_settings(db_session, dividends_module_enabled=True)
    first = make_member(db_session, psn="PSN-1", email="one@example.com")
    second = make_member(db_session, psn="PSN-2", email="two@example.com")
    run = models.DividendRun(
        fiscal_year=2025,
        period_start=date(2025, 1, 1),
        period_end=date(2025, 12, 31),
        status=models.DividendRunStatus.DECLARED,
        basis=models.DividendBasis.NET_SAVINGS_CLOSING,
        pool_mode=models.DividendPoolMode.NET_INCOME_SHARE,
        pool_amount=Decimal("1000.00"),
        declared_on=date(2026, 1, 5),
    )
    db_session.add(run)
    db_session.flush()
    payout = models.DividendPayout(
        run_id=run.id,
        paid_on=date(2026, 1, 6),
        method=models.DividendPayoutMethod.BANK,
        reference="TRF-1",
        amount=Decimal("400.00"),
    )
    db_session.add(payout)
    db_session.flush()
    db_session.add_all([
        models.DividendAllocation(
            run_id=run.id, member_id=first.id,
            basis_amount=Decimal("600.00"), share_ratio=Decimal("0.6"),
            gross_amount=Decimal("600.00"), withholding_amount=ZERO,
            net_amount=Decimal("600.00"), rounding_adjustment=ZERO,
        ),
        models.DividendAllocation(
            run_id=run.id, member_id=second.id,
            basis_amount=Decimal("400.00"), share_ratio=Decimal("0.4"),
            gross_amount=Decimal("400.00"), withholding_amount=ZERO,
            net_amount=Decimal("400.00"), rounding_adjustment=ZERO,
            payout_id=payout.id,
        ),
    ])
    db_session.commit()

    dividends = _dashboard(client, admin)["dividends"]

    assert dividends["last_declared_year"] == 2025
    assert Decimal(dividends["last_pool"]) == Decimal("1000.00")
    assert Decimal(dividends["unpaid_net"]) == Decimal("600.00")
    assert Decimal(dividends["paid_net"]) == Decimal("400.00")


def test_queues_only_list_actions_the_officer_can_take(client, db_session):
    admin = _admin(db_session, "loan.review", "repayment.verify")
    member = make_member(db_session)
    loan_type = make_loan_type(db_session, "Salary Loan")
    loan = _loan(db_session, member, loan_type)

    reviewable = models.LoanApplication(
        member_id=member.id,
        loan_type_id=loan_type.id,
        requested_amount=Decimal("1000.00"),
        form_fee_amount=ZERO,
        payment_reference="TRF-FEE-1",
        receipt_image_base64="aGVsbG8=",
        receipt_content_type="image/png",
        status=models.LoanApplicationStatus.PENDING,
        payment_status=models.PaymentVerificationStatus.VERIFIED,
    )
    unpaid_fee = models.LoanApplication(
        member_id=member.id,
        loan_type_id=loan_type.id,
        requested_amount=Decimal("800.00"),
        form_fee_amount=ZERO,
        payment_reference="TRF-FEE-2",
        receipt_image_base64="aGVsbG8=",
        receipt_content_type="image/png",
        status=models.LoanApplicationStatus.PENDING,
        payment_status=models.PaymentVerificationStatus.AWAITING_VERIFICATION,
    )
    db_session.add_all([reviewable, unpaid_fee])
    db_session.add(
        models.LoanRepayment(
            loan_id=loan.id,
            member_id=member.id,
            payment_month=date.today().replace(day=1),
            amount_claimed=Decimal("100.00"),
            payment_reference="TRF-2",
            receipt_image_base64="aGVsbG8=",
            receipt_content_type="image/png",
        )
    )
    db_session.commit()

    queues = {item["key"]: item for item in _dashboard(client, admin)["queues"]}

    assert queues["applications_review"]["count"] == 1
    assert queues["applications_review"]["href"] == "/admin/loan-applications?queue=review"
    assert queues["application_payments"]["count"] == 1
    assert queues["application_payments"]["href"] == "/admin/loan-applications?queue=payment"
    assert queues["repayments"]["count"] == 1
    assert queues["repayments"]["href"] == "/admin/loan-repayments?status=awaiting_verification"
    assert "disbursements" not in queues  # no disbursement.submit
    assert "settlements" not in queues  # no savings.settle


def test_disbursement_queue_excludes_applications_already_turned_into_loans(
    client, db_session
):
    admin = _admin(db_session, "disbursement.submit")
    member = make_member(db_session)
    loan_type = make_loan_type(db_session, "Dashboard Loan")
    loan = _loan(db_session, member, loan_type)
    common = {
        "member_id": member.id,
        "loan_type_id": loan_type.id,
        "requested_amount": Decimal("1000.00"),
        "form_fee_amount": ZERO,
        "receipt_image_base64": "aGVsbG8=",
        "receipt_content_type": "image/png",
        "status": models.LoanApplicationStatus.APPROVED,
        "payment_status": models.PaymentVerificationStatus.VERIFIED,
    }
    db_session.add_all(
        [
            models.LoanApplication(**common, payment_reference="TRF-AWAITING"),
            models.LoanApplication(
                **common,
                payment_reference="TRF-DISBURSED",
                resulting_loan_id=loan.id,
            ),
        ]
    )
    db_session.commit()

    queues = {item["key"]: item for item in _dashboard(client, admin)["queues"]}

    assert queues["disbursements"]["count"] == 1
    assert queues["disbursements"]["href"] == "/admin/disbursements"


def test_settlement_queue_links_to_pending_payouts(client, db_session):
    admin = _admin(db_session, "savings.settle")
    member = make_member(db_session)
    db_session.add(
        models.MemberSettlement(
            member_id=member.id,
            settled_on=date(2026, 10, 1),
            savings_balance=Decimal("500.00"),
            offset_total=ZERO,
            payout_amount=Decimal("500.00"),
            payout_status=models.SettlementPayoutStatus.PENDING,
        )
    )
    db_session.commit()

    queues = {item["key"]: item for item in _dashboard(client, admin)["queues"]}

    assert queues["settlements"]["count"] == 1
    assert Decimal(queues["settlements"]["amount"]) == Decimal("500.00")
    assert queues["settlements"]["href"] == "/members?settlement=pending"


def test_activity_and_trend_are_permission_gated(client, db_session):
    admin = _admin(db_session, "audit.view", "savings.view")
    member = make_member(db_session)
    _contribution(db_session, member, "1000.00")
    older = models.AuditEvent(event_type="member.create", action="create", timestamp=datetime.utcnow() - timedelta(hours=2))
    newer = models.AuditEvent(event_type="loan.approve", action="approve", timestamp=datetime.utcnow() - timedelta(hours=1))
    db_session.add_all([older, newer])
    db_session.commit()

    body = _dashboard(client, admin)

    assert [row["event_type"] for row in body["activity"]] == ["loan.approve", "member.create"]
    trend = body["trend"]
    assert len(trend["months"]) == 6
    assert trend["months"][-1] == date.today().strftime("%Y-%m")
    assert Decimal(trend["savings"][-1]) == Decimal("1000.00")
    assert trend["repayments"] is None


def test_unknown_period_is_rejected(client, db_session):
    admin = _admin(db_session, "member.view")

    response = client.get(
        "/api/admin/dashboard?period=last_week", headers=auth_headers(admin)
    )

    assert response.status_code == 422
