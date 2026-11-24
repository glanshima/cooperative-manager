"""Dividends: a closed year's surplus, appropriated and paid out.

What these tests pin down:
  - the pool comes out of the year's surplus after reserve and honorarium,
    and the shares always sum to the pool exactly, whatever the basis or
    rounding;
  - declaring is one transaction: the year closes into retained earnings
    and the appropriation posts in the same moment, and a closed year
    still reports its income and expenditure;
  - a declared run is immutable -- no recompute, no second declare -- and
    a payout clears the member liability net of withholding;
  - every guard refuses before touching the ledger: module off, no basis,
    no opening balances, a locked month, a stale draft, a loss year, a
    split that does not total 100, a pool larger than the surplus;
  - eligibility follows the accepted policy: financial members, a nonzero
    basis, exited members out unless included, the minimum months rule.

The chart of accounts is seeded by the production migration; here the test
creates it so the suite does not depend on migration order.
"""
from datetime import date, datetime, time
from decimal import Decimal

from app import cashbook, dividends, models
from tests.conftest import (
    auth_headers,
    grant_permission,
    make_admin_user,
    make_loan_type,
    make_member,
    make_settings,
)

ZERO = Decimal("0.00")
RETAINED = "RETAINED_EARNINGS"
EXPENSE_CODE = "5010"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _ensure_chart(db_session):
    existing = {account.code for account in db_session.query(models.CashbookAccount).all()}
    chart = [
        ("1000", "Cash on hand", models.CashbookAccountKind.ASSET, cashbook.CASH),
        ("1010", "Bank", models.CashbookAccountKind.ASSET, cashbook.BANK),
        ("1100", "Loans receivable", models.CashbookAccountKind.ASSET, cashbook.LOAN_RECEIVABLE),
        ("2000", "Member savings", models.CashbookAccountKind.LIABILITY, cashbook.MEMBER_SAVINGS),
        ("2010", "Payouts payable", models.CashbookAccountKind.LIABILITY, cashbook.PAYOUT_PAYABLE),
        (
            "2020",
            "Other deductions payable",
            models.CashbookAccountKind.LIABILITY,
            cashbook.OTHER_DEDUCTIONS_PAYABLE,
        ),
        (
            "2030",
            "Dividends payable",
            models.CashbookAccountKind.LIABILITY,
            dividends.DIVIDENDS_PAYABLE,
        ),
        (
            "2040",
            "Honorarium payable",
            models.CashbookAccountKind.LIABILITY,
            dividends.HONORARIUM_PAYABLE,
        ),
        (
            "2050",
            "Withholding payable",
            models.CashbookAccountKind.LIABILITY,
            dividends.WITHHOLDING_PAYABLE,
        ),
        ("3000", "Retained earnings", models.CashbookAccountKind.EQUITY, RETAINED),
        ("3010", "Reserve", models.CashbookAccountKind.EQUITY, dividends.RESERVE),
        ("4000", "Loan interest income", models.CashbookAccountKind.INCOME, cashbook.INTEREST_INCOME),
        ("4010", "Loan fee income", models.CashbookAccountKind.INCOME, cashbook.LOAN_FEE_INCOME),
        (EXPENSE_CODE, "Administrative expenses", models.CashbookAccountKind.EXPENSE, None),
    ]
    for code, name, kind, system_key in chart:
        if code in existing:
            continue
        db_session.add(
            models.CashbookAccount(code=code, name=name, kind=kind, system_key=system_key)
        )
    db_session.commit()


def _enable(db_session, **extra):
    options = {
        "cashbook_module_enabled": True,
        "dividends_module_enabled": True,
        "dividend_basis": models.DividendBasis.NET_SAVINGS_CLOSING,
    }
    options.update(extra)
    return make_settings(db_session, **options)


def _acct(db_session, key):
    return db_session.query(models.CashbookAccount).filter_by(system_key=key).one()


def _by_code(db_session, code):
    return db_session.query(models.CashbookAccount).filter_by(code=code).one()


def _post(db_session, day, lines, *, source=models.CashbookEntrySource.MANUAL, source_id=None,
          narration="Test entry"):
    entry = cashbook.post(
        db_session,
        entry_date=day,
        narration=narration,
        lines=lines,
        source=source,
        source_id=source_id,
    )
    db_session.commit()
    return entry


def _opening(db_session, amount="100000.00"):
    """An opening journal: bank against retained earnings, dated before
    every fiscal year the tests use."""
    _post(
        db_session,
        date(2024, 12, 31),
        [
            (_acct(db_session, cashbook.BANK), Decimal(amount), ZERO),
            (_acct(db_session, RETAINED), ZERO, Decimal(amount)),
        ],
        source=models.CashbookEntrySource.OPENING,
        narration="Opening balances",
    )


def _income(db_session, amount, day=date(2025, 6, 30)):
    _post(
        db_session,
        day,
        [
            (_acct(db_session, cashbook.BANK), Decimal(amount), ZERO),
            (_acct(db_session, cashbook.INTEREST_INCOME), ZERO, Decimal(amount)),
        ],
    )


def _expense(db_session, amount, day=date(2025, 7, 15)):
    _post(
        db_session,
        day,
        [
            (_by_code(db_session, EXPENSE_CODE), Decimal(amount), ZERO),
            (_acct(db_session, cashbook.BANK), ZERO, Decimal(amount)),
        ],
    )


def _credit_savings(db_session, member, amount, when=date(2025, 3, 31)):
    db_session.add(
        models.SavingsEntry(
            member_id=member.id,
            entry_type=models.SavingsEntryType.CONTRIBUTION,
            amount=Decimal(amount),
            posted_at=datetime.combine(when, time(9, 0)),
            note="Test contribution",
        )
    )
    db_session.commit()


def _member(db_session, psn, *, status=models.MemberStatus.FINANCIAL, created=date(2024, 1, 1), **extra):
    return make_member(
        db_session,
        psn=psn,
        name=f"Member {psn}",
        email=f"{psn.lower()}@example.com",
        status=status,
        created_at=datetime.combine(created, time(9, 0)),
        **extra,
    )


def _books(db_session, *, income="4000.00", expense="1000.00", **settings):
    """Chart, module on, opening journal, two contributing members, and a
    year whose surplus is 3000 by default (pool 2769)."""
    _ensure_chart(db_session)
    _enable(db_session, **settings)
    _opening(db_session)
    m1 = _member(db_session, "PSN-0001")
    m2 = _member(db_session, "PSN-0002")
    _credit_savings(db_session, m1, "6000.00")
    _credit_savings(db_session, m2, "4000.00")
    if Decimal(income) > ZERO:
        _income(db_session, income)
    if Decimal(expense) > ZERO:
        _expense(db_session, expense)
    return m1, m2


def _admin(db_session, username="div_admin"):
    return make_admin_user(db_session, username=username, super_admin=True)


def _draft(client, admin, year=2025, *, expect=201):
    response = client.post(
        "/api/dividends/runs", json={"fiscal_year": year}, headers=auth_headers(admin)
    )
    assert response.status_code == expect, response.text
    return response.json()


def _declare(client, admin, run_id, declared_on="2026-01-05", *, expect=200):
    response = client.post(
        f"/api/dividends/runs/{run_id}/declare",
        json={"declared_on": declared_on},
        headers=auth_headers(admin),
    )
    assert response.status_code == expect, response.text
    return response.json()


def _allocations(client, admin, run_id):
    response = client.get(
        f"/api/dividends/runs/{run_id}/allocations?limit=200",
        headers=auth_headers(admin),
    )
    assert response.status_code == 200, response.text
    return {row["psn"]: row for row in response.json()["items"]}


def _balance(db_session, system_key):
    db_session.expire_all()
    return cashbook.account_ledger(db_session, _acct(db_session, system_key)).closing_balance


def _run(db_session, run_id):
    db_session.expire_all()
    return db_session.query(models.DividendRun).filter_by(id=run_id).one()


# ---------------------------------------------------------------------------
# Computation
# ---------------------------------------------------------------------------

def test_the_draft_takes_the_pool_out_of_the_surplus_and_splits_by_savings(client, db_session):
    _books(db_session)
    admin = _admin(db_session)

    body = _draft(client, admin)

    assert body["status"] == "draft"
    assert Decimal(body["surplus"]) == Decimal("3000.00")
    assert Decimal(body["reserve_amount"]) == Decimal("141.00")
    assert Decimal(body["honorarium_amount"]) == Decimal("90.00")
    assert Decimal(body["pool_amount"]) == Decimal("2769.00")
    assert Decimal(body["total_gross"]) == Decimal("2769.00")
    assert body["eligible_member_count"] == 2

    rows = _allocations(client, admin, body["id"])
    assert Decimal(rows["PSN-0001"]["basis_amount"]) == Decimal("6000.00")
    assert Decimal(rows["PSN-0002"]["basis_amount"]) == Decimal("4000.00")
    assert Decimal(rows["PSN-0001"]["share_ratio"]) == Decimal("0.6")
    assert Decimal(rows["PSN-0001"]["gross_amount"]) == Decimal("1661.40")
    assert Decimal(rows["PSN-0002"]["gross_amount"]) == Decimal("1107.60")


def test_the_summary_reports_the_policy_and_the_run_sequence(client, db_session):
    _books(db_session)
    admin = _admin(db_session)

    body = client.get("/api/dividends/summary", headers=auth_headers(admin)).json()
    assert body["basis"] == "net_savings_closing"
    assert body["cashbook_module_enabled"] is True
    assert body["cashbook_open"] is True
    assert body["last_declared_year"] is None

    run = _draft(client, admin)
    _declare(client, admin, run["id"])

    after = client.get("/api/dividends/summary", headers=auth_headers(admin)).json()
    assert after["last_declared_year"] == 2025
    assert after["suggested_fiscal_year"] == 2026


def test_equal_basis_gives_every_member_the_same_share_and_keeps_the_pool_total(client, db_session):
    _ensure_chart(db_session)
    _enable(db_session, dividend_basis=models.DividendBasis.EQUAL)
    _opening(db_session)
    for psn in ("PSN-0001", "PSN-0002", "PSN-0003"):
        _member(db_session, psn)
    _income(db_session, "1000.00")
    admin = _admin(db_session)

    body = _draft(client, admin)

    assert Decimal(body["pool_amount"]) == Decimal("923.00")
    rows = _allocations(client, admin, body["id"])
    amounts = sorted(Decimal(row["gross_amount"]) for row in rows.values())
    assert amounts == [Decimal("307.66"), Decimal("307.67"), Decimal("307.67")]
    assert sum(amounts) == Decimal("923.00")
    assert Decimal(body["rounding_residual"]) == Decimal("0.00")


def test_whole_currency_rounding_keeps_the_pool_total(client, db_session):
    _books(db_session, dividend_rounding=models.DividendRounding.WHOLE_CURRENCY)
    admin = _admin(db_session)

    body = _draft(client, admin)

    rows = _allocations(client, admin, body["id"])
    amounts = {psn: Decimal(row["gross_amount"]) for psn, row in rows.items()}
    assert amounts == {"PSN-0001": Decimal("1661"), "PSN-0002": Decimal("1108")}
    assert sum(amounts.values()) == Decimal("2769.00")


def test_average_savings_basis_uses_the_month_end_balances(client, db_session):
    _ensure_chart(db_session)
    _enable(db_session, dividend_basis=models.DividendBasis.NET_SAVINGS_AVERAGE)
    _opening(db_session)
    m1 = _member(db_session, "PSN-0001")
    m2 = _member(db_session, "PSN-0002")
    _credit_savings(db_session, m1, "6000.00", when=date(2025, 3, 31))
    _credit_savings(db_session, m1, "4000.00", when=date(2025, 9, 30))
    _credit_savings(db_session, m2, "4000.00", when=date(2025, 9, 30))
    _income(db_session, "4000.00")
    _expense(db_session, "1000.00")
    admin = _admin(db_session)

    body = _draft(client, admin)
    rows = _allocations(client, admin, body["id"])

    # 36,000 over six months plus 40,000 over four months, over twelve.
    assert Decimal(rows["PSN-0001"]["basis_amount"]) == Decimal("6333.33")
    # Four months at 4,000 over twelve.
    assert Decimal(rows["PSN-0002"]["basis_amount"]) == Decimal("1333.33")


def test_patronage_basis_uses_the_interest_collected_in_the_year(client, db_session):
    _ensure_chart(db_session)
    _enable(db_session, dividend_basis=models.DividendBasis.PATRONAGE)
    _opening(db_session)
    m1 = _member(db_session, "PSN-0001")
    m2 = _member(db_session, "PSN-0002")
    loan_type = make_loan_type(db_session, "Patronage loan")
    _make_loan_row(db_session, m1, loan_type)
    _income(db_session, "4000.00")
    _expense(db_session, "1000.00")
    admin = _admin(db_session)

    body = _draft(client, admin)

    rows = _allocations(client, admin, body["id"])
    assert set(rows) == {"PSN-0001"}
    assert Decimal(rows["PSN-0001"]["basis_amount"]) == Decimal("500.00")
    assert Decimal(rows["PSN-0001"]["gross_amount"]) == Decimal("2769.00")


def test_hybrid_basis_blends_savings_and_patronage(client, db_session):
    _ensure_chart(db_session)
    _enable(db_session, dividend_basis=models.DividendBasis.HYBRID)
    _opening(db_session)
    m1 = _member(db_session, "PSN-0001")
    m2 = _member(db_session, "PSN-0002")
    _credit_savings(db_session, m1, "6000.00")
    _credit_savings(db_session, m2, "4000.00")
    loan_type = make_loan_type(db_session, "Patronage loan")
    _make_loan_row(db_session, m1, loan_type)
    _income(db_session, "4000.00")
    _expense(db_session, "1000.00")
    admin = _admin(db_session)

    body = _draft(client, admin)

    rows = _allocations(client, admin, body["id"])
    # 0.5 split: M1 = 0.5*0.6 + 0.5*1.0 = 0.8; M2 = 0.5*0.4 = 0.2.
    assert Decimal(rows["PSN-0001"]["gross_amount"]) == Decimal("2215.20")
    assert Decimal(rows["PSN-0002"]["gross_amount"]) == Decimal("553.80")
    assert Decimal(body["total_gross"]) == Decimal("2769.00")


def _make_loan_row(db_session, member, loan_type, *, interest="500.00", disbursed=date(2025, 3, 1)):
    loan = models.Loan(
        member_id=member.id,
        loan_type_id=loan_type.id,
        principal=Decimal("1000.00"),
        interest_amount=Decimal(interest),
        net_disbursed=Decimal("1000.00"),
        total_repayable=Decimal("1000.00") + Decimal(interest),
        monthly_installment=Decimal("100.00"),
        interest_mode=models.InterestDeductionMode.AT_SOURCE,
        disbursement_date=disbursed,
        expected_end_date=date(disbursed.year + 1, disbursed.month, 1),
        amount_repaid=ZERO,
        status=models.LoanStatus.ACTIVE,
    )
    db_session.add(loan)
    db_session.commit()
    db_session.refresh(loan)
    return loan


def test_eligibility_skips_non_financial_zero_basis_recent_and_exited_members(client, db_session):
    _ensure_chart(db_session)
    _enable(db_session, dividend_min_membership_months=6)
    _opening(db_session)
    payer = _member(db_session, "PSN-0001")
    _credit_savings(db_session, payer, "6000.00")
    non_financial = _member(db_session, "PSN-0002", status=models.MemberStatus.NON_FINANCIAL)
    _credit_savings(db_session, non_financial, "4000.00")
    recent = _member(db_session, "PSN-0003", created=date(2025, 12, 15))
    _credit_savings(db_session, recent, "4000.00")
    empty = _member(db_session, "PSN-0004")
    exited = _member(db_session, "PSN-0005", membership_exit_date=date(2025, 6, 30))
    _credit_savings(db_session, exited, "4000.00")
    _income(db_session, "4000.00")
    _expense(db_session, "1000.00")
    admin = _admin(db_session)

    body = _draft(client, admin)

    assert body["eligible_member_count"] == 1
    rows = _allocations(client, admin, body["id"])
    assert set(rows) == {"PSN-0001"}
    assert Decimal(rows["PSN-0001"]["gross_amount"]) == Decimal("2769.00")


def test_an_exited_member_can_be_included_by_policy(client, db_session):
    _ensure_chart(db_session)
    _enable(db_session, dividend_include_exited=True)
    _opening(db_session)
    exited = _member(db_session, "PSN-0005", membership_exit_date=date(2025, 6, 30))
    _credit_savings(db_session, exited, "4000.00")
    _income(db_session, "4000.00")
    _expense(db_session, "1000.00")
    admin = _admin(db_session)

    body = _draft(client, admin)

    rows = _allocations(client, admin, body["id"])
    assert set(rows) == {"PSN-0005"}


# ---------------------------------------------------------------------------
# Declaration and payout
# ---------------------------------------------------------------------------

def test_declaring_closes_the_year_and_appropriates_the_surplus(client, db_session):
    _books(db_session)
    admin = _admin(db_session)
    run = _draft(client, admin)

    body = _declare(client, admin, run["id"])

    assert body["status"] == "declared"
    assert body["declared_on"] == "2026-01-05"

    # The appropriation moved the surplus out of retained earnings.
    assert _balance(db_session, RETAINED) == Decimal("100000.00")
    assert _balance(db_session, dividends.RESERVE) == Decimal("141.00")
    assert _balance(db_session, dividends.HONORARIUM_PAYABLE) == Decimal("90.00")
    assert _balance(db_session, dividends.DIVIDENDS_PAYABLE) == Decimal("2769.00")

    # The closing entry is one balanced entry dated the year end.
    closes = (
        db_session.query(models.CashbookEntry)
        .filter(models.CashbookEntry.source == models.CashbookEntrySource.YEAR_CLOSE)
        .all()
    )
    assert len(closes) == 1
    assert closes[0].entry_date == date(2025, 12, 31)
    declarations = (
        db_session.query(models.CashbookEntry)
        .filter(models.CashbookEntry.source == models.CashbookEntrySource.DIVIDEND_DECLARATION)
        .all()
    )
    assert len(declarations) == 1
    assert declarations[0].entry_date == date(2026, 1, 5)

    # A closed year still reports what it earned and spent.
    statement = cashbook.income_statement(db_session, start=date(2025, 1, 1), end=date(2025, 12, 31))
    assert statement.surplus == Decimal("3000.00")

    sheet = cashbook.balance_sheet(db_session, as_of=date(2026, 1, 5))
    assert sheet.total_assets == sheet.total_liabilities + sheet.total_equity


def test_a_payout_clears_the_liability_and_keeps_the_withholding(client, db_session):
    _books(db_session, dividend_withholding_pct=Decimal("10.00"))
    admin = _admin(db_session)
    run = _draft(client, admin)
    _declare(client, admin, run["id"])

    response = client.post(
        f"/api/dividends/runs/{run['id']}/payouts",
        json={
            "paid_on": "2026-01-10",
            "method": "bank",
            "reference": "DIV-2025",
        },
        headers=auth_headers(admin),
    )

    assert response.status_code == 201, response.text
    payout = response.json()
    assert Decimal(payout["amount"]) == Decimal("2492.10")

    payload = _allocations(client, admin, run["id"])
    assert Decimal(payload["PSN-0001"]["withholding_amount"]) == Decimal("166.14")
    assert Decimal(payload["PSN-0002"]["withholding_amount"]) == Decimal("110.76")

    assert _balance(db_session, dividends.DIVIDENDS_PAYABLE) == ZERO
    assert _balance(db_session, dividends.WITHHOLDING_PAYABLE) == Decimal("276.90")
    assert _balance(db_session, cashbook.BANK) == Decimal("100507.90")
    assert _run(db_session, run["id"]).status == models.DividendRunStatus.PAID


def test_the_manifest_totals_match_the_allocations(client, db_session):
    _books(db_session)
    admin = _admin(db_session)
    run = _draft(client, admin)
    _declare(client, admin, run["id"])

    body = client.get(
        f"/api/dividends/runs/{run['id']}/manifest", headers=auth_headers(admin)
    ).json()

    assert body["fiscal_year"] == 2025
    assert [row["psn"] for row in body["rows"]] == ["PSN-0001", "PSN-0002"]
    assert Decimal(body["total_gross"]) == Decimal("2769.00")
    assert Decimal(body["total_gross"]) == sum(
        Decimal(row["gross_amount"]) for row in body["rows"]
    )
    assert Decimal(body["total_net"]) == Decimal("2769.00")


def test_a_declared_run_cannot_be_declared_or_recomputed_again(client, db_session):
    _books(db_session)
    admin = _admin(db_session)
    run = _draft(client, admin)
    _declare(client, admin, run["id"])

    again = client.post(
        f"/api/dividends/runs/{run['id']}/declare",
        json={"declared_on": "2026-01-06"},
        headers=auth_headers(admin),
    )
    assert again.status_code == 409

    recompute = client.patch(
        f"/api/dividends/runs/{run['id']}", json={"note": "later"}, headers=auth_headers(admin)
    )
    assert recompute.status_code == 409

    second_year = client.post(
        "/api/dividends/runs", json={"fiscal_year": 2025}, headers=auth_headers(admin)
    )
    assert second_year.status_code == 409


def test_a_stale_draft_must_be_refreshed_before_declaring(client, db_session):
    _books(db_session)
    admin = _admin(db_session)
    run = _draft(client, admin)

    _income(db_session, "1000.00", day=date(2025, 8, 1))

    stale = client.post(
        f"/api/dividends/runs/{run['id']}/declare",
        json={"declared_on": "2026-01-05"},
        headers=auth_headers(admin),
    )
    assert stale.status_code == 409
    assert "changed" in stale.json()["detail"]

    refreshed = client.patch(
        f"/api/dividends/runs/{run['id']}", json={}, headers=auth_headers(admin)
    )
    assert refreshed.status_code == 200, refreshed.text
    assert Decimal(refreshed.json()["surplus"]) == Decimal("4000.00")

    _declare(client, admin, run["id"])


def test_a_payout_batch_can_cover_a_subset_of_the_members(client, db_session):
    _books(db_session)
    admin = _admin(db_session)
    run = _draft(client, admin)
    _declare(client, admin, run["id"])
    rows = _allocations(client, admin, run["id"])

    first = client.post(
        f"/api/dividends/runs/{run['id']}/payouts",
        json={
            "paid_on": "2026-01-10",
            "method": "bank",
            "reference": "DIV-2025-A",
            "allocation_ids": [rows["PSN-0001"]["id"]],
        },
        headers=auth_headers(admin),
    )
    assert first.status_code == 201, first.text
    assert Decimal(first.json()["amount"]) == Decimal("1661.40")
    assert _run(db_session, run["id"]).status == models.DividendRunStatus.DECLARED

    rest = client.post(
        f"/api/dividends/runs/{run['id']}/payouts",
        json={
            "paid_on": "2026-01-11",
            "method": "bank",
            "reference": "DIV-2025-B",
        },
        headers=auth_headers(admin),
    )
    assert rest.status_code == 201, rest.text
    assert Decimal(rest.json()["amount"]) == Decimal("1107.60")
    assert _run(db_session, run["id"]).status == models.DividendRunStatus.PAID

    nothing_left = client.post(
        f"/api/dividends/runs/{run['id']}/payouts",
        json={"paid_on": "2026-01-12", "method": "bank", "reference": "DIV-2025-C"},
        headers=auth_headers(admin),
    )
    assert nothing_left.status_code == 409


def test_the_payment_policy_restricts_the_method(client, db_session):
    _books(db_session, dividend_payment_method=models.DividendPaymentPolicy.BANK)
    admin = _admin(db_session)
    run = _draft(client, admin)
    _declare(client, admin, run["id"])

    cash = client.post(
        f"/api/dividends/runs/{run['id']}/payouts",
        json={"paid_on": "2026-01-10", "method": "cash", "reference": "DIV-2025"},
        headers=auth_headers(admin),
    )
    assert cash.status_code == 400


# ---------------------------------------------------------------------------
# Guards
# ---------------------------------------------------------------------------

def test_the_module_toggle_gates_every_route(client, db_session):
    make_settings(db_session, cashbook_module_enabled=True, dividends_module_enabled=False)
    admin = _admin(db_session)

    response = client.get("/api/dividends/summary", headers=auth_headers(admin))

    assert response.status_code == 403
    assert client.get("/api/dividends/runs", headers=auth_headers(admin)).status_code == 403


def test_no_basis_means_no_run(client, db_session):
    _ensure_chart(db_session)
    _enable(db_session, dividend_basis=models.DividendBasis.NONE)
    _opening(db_session)
    admin = _admin(db_session)

    body = _draft(client, admin, expect=409)

    assert "basis" in body["detail"]


def test_share_capital_basis_is_refused(client, db_session):
    _ensure_chart(db_session)
    _enable(db_session, dividend_basis=models.DividendBasis.SHARE_CAPITAL)
    _opening(db_session)
    admin = _admin(db_session)

    _draft(client, admin, expect=409)


def test_the_split_must_total_one_hundred(client, db_session):
    _books(
        db_session,
        dividend_reserve_pct=Decimal("10.00"),
        dividend_honorarium_pct=Decimal("10.00"),
        dividend_payout_pct=Decimal("70.00"),
    )
    admin = _admin(db_session)

    body = _draft(client, admin, expect=409)

    assert "100" in body["detail"]


def test_the_pool_cannot_exceed_the_distributable_surplus(client, db_session):
    _books(
        db_session,
        dividend_pool_mode=models.DividendPoolMode.FIXED_AMOUNT,
        dividend_fixed_pool_amount=Decimal("5000.00"),
    )
    admin = _admin(db_session)

    body = _draft(client, admin, expect=409)

    assert "exceeds" in body["detail"]


def test_a_loss_year_produces_an_empty_run(client, db_session):
    _ensure_chart(db_session)
    _enable(db_session)
    _opening(db_session)
    _member(db_session, "PSN-0001")
    _income(db_session, "1000.00")
    _expense(db_session, "3000.00")
    admin = _admin(db_session)

    body = _draft(client, admin)

    assert Decimal(body["surplus"]) == Decimal("-2000.00")
    assert Decimal(body["pool_amount"]) == ZERO
    assert body["eligible_member_count"] == 0
    assert _allocations(client, admin, body["id"]) == {}


def test_a_run_with_no_basis_for_anyone_is_refused(client, db_session):
    _ensure_chart(db_session)
    _enable(db_session)
    _opening(db_session)
    _member(db_session, "PSN-0001")
    _income(db_session, "4000.00")
    _expense(db_session, "1000.00")
    admin = _admin(db_session)

    _draft(client, admin, expect=409)


def test_declaring_waits_for_the_opening_balances(client, db_session):
    _ensure_chart(db_session)
    _enable(db_session)
    _member(db_session, "PSN-0001")
    _credit_savings(db_session, _member(db_session, "PSN-0002"), "6000.00")
    _income(db_session, "4000.00")
    _expense(db_session, "1000.00")
    admin = _admin(db_session)
    run = _draft(client, admin)

    body = _declare(client, admin, run["id"], expect=409)

    assert "opening" in body["detail"].lower()


def test_a_locked_month_blocks_the_closing_entry(client, db_session):
    _books(db_session)
    admin = _admin(db_session)
    run = _draft(client, admin)
    cashbook.lock_period(db_session, date(2025, 12, 1))
    db_session.commit()

    body = _declare(client, admin, run["id"], expect=409)

    assert "locked" in body["detail"].lower()


def test_income_before_the_first_year_blocks_the_run(client, db_session):
    _books(db_session)
    _income(db_session, "500.00", day=date(2024, 6, 30))
    admin = _admin(db_session)

    body = _draft(client, admin, expect=409)

    assert "before the year starts" in body["detail"]


def test_years_are_declared_in_sequence(client, db_session):
    _books(db_session)
    admin = _admin(db_session)
    run = _draft(client, admin)
    _declare(client, admin, run["id"])

    body = _draft(client, admin, year=2027, expect=409)

    assert "2026" in body["detail"]


def test_declaring_refuses_when_retained_earnings_would_not_cover_it(client, db_session):
    _books(db_session)
    # A manual equity debit inside the year leaves retained earnings short.
    _post(
        db_session,
        date(2025, 6, 30),
        [
            (_acct(db_session, RETAINED), Decimal("200000.00"), ZERO),
            (_acct(db_session, cashbook.BANK), ZERO, Decimal("200000.00")),
        ],
    )
    admin = _admin(db_session)
    run = _draft(client, admin)

    body = _declare(client, admin, run["id"], expect=409)

    assert "Retained earnings" in body["detail"]


def test_permissions_split_viewing_declaring_and_paying(client, db_session, seed_permissions):
    _books(db_session)
    viewer = make_admin_user(db_session, username="div_viewer")
    grant_permission(db_session, viewer, "dividend.view")
    assert client.get("/api/dividends/runs", headers=auth_headers(viewer)).status_code == 200
    assert (
        client.post(
            "/api/dividends/runs", json={"fiscal_year": 2025}, headers=auth_headers(viewer)
        ).status_code
        == 403
    )

    payer = make_admin_user(db_session, username="div_payer")
    grant_permission(db_session, payer, "dividend.pay")
    assert client.get("/api/dividends/runs", headers=auth_headers(payer)).status_code == 403

    outsider = make_admin_user(db_session, username="div_outsider")
    assert client.get("/api/dividends/runs", headers=auth_headers(outsider)).status_code == 403
