"""Cashbook: the double-entry ledger, its automatic postings and its reports.

What these tests pin down:
  - the module toggle gates every route, and nothing posts until the
    opening journal exists;
  - an entry is balanced or it is not posted, and a correction is a
    reversing entry, never an edit;
  - a locked month refuses new entries until it is unlocked;
  - confirming payroll, disbursing/repaying a loan, verifying a fee and
    settling an exit all post their own journal entries, keyed to the row
    that caused them so a repeat can never double the books;
  - the trial balance, income & expenditure, balance sheet, account ledger
    and cash register agree with the journal.

The chart of accounts is seeded by the production migration; here it is
created by the test so the suite does not depend on migration order.
"""
import uuid
from datetime import date
from decimal import Decimal

from app import cashbook, models
from tests.conftest import (
    auth_headers,
    grant_permission,
    make_admin_user,
    make_loan_type,
    make_member,
    make_member_user,
    make_settings,
)

ZERO = Decimal("0.00")
RETAINED = "RETAINED_EARNINGS"
EXPENSE_CODE = "5010"


def _ensure_chart(db_session):
    """Insert the starter chart the migration seeds in production."""
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
        ("3000", "Retained earnings", models.CashbookAccountKind.EQUITY, RETAINED),
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
    return make_settings(db_session, cashbook_module_enabled=True, **extra)


def _accounts(db_session):
    rows = (
        db_session.query(models.CashbookAccount)
        .filter(models.CashbookAccount.system_key.isnot(None))
        .all()
    )
    return {account.system_key: account for account in rows}


def _account_by_code(db_session, code):
    return db_session.query(models.CashbookAccount).filter(models.CashbookAccount.code == code).one()


def _opening_body(db_session, *, bank="10000.00", cash="0.00", as_of="2025-12-31"):
    accounts = _accounts(db_session)
    lines = []
    if Decimal(cash) > ZERO:
        lines.append({"account_id": str(accounts[cashbook.CASH].id), "debit": cash, "credit": "0"})
    lines.append({"account_id": str(accounts[cashbook.BANK].id), "debit": bank, "credit": "0"})
    lines.append(
        {
            "account_id": str(accounts[RETAINED].id),
            "debit": "0",
            "credit": str(Decimal(bank) + Decimal(cash)),
        }
    )
    return {"as_of": as_of, "note": "Brought forward", "lines": lines}


def _opening(client, admin, db_session, *, bank="10000.00", cash="0.00", as_of="2025-12-31"):
    response = client.post(
        "/api/cashbook/opening",
        json=_opening_body(db_session, bank=bank, cash=cash, as_of=as_of),
        headers=auth_headers(admin),
    )
    assert response.status_code == 201, response.text
    return response.json()


def _ready(client, db_session, *, username="cb_admin", bank="10000.00", cash="0.00"):
    """Module on, chart present, opening posted, super-admin caller."""
    _enable(db_session)
    _ensure_chart(db_session)
    admin = make_admin_user(db_session, username=username, super_admin=True)
    _opening(client, admin, db_session, bank=bank, cash=cash)
    return admin


def _manual(
    client,
    admin,
    db_session,
    *,
    debit,
    credit,
    amount,
    entry_date=None,
    narration="Manual entry",
):
    payload = {
        "entry_date": (entry_date or date.today()).isoformat(),
        "narration": narration,
        "lines": [
            {"account_id": str(debit.id), "debit": str(amount), "credit": "0"},
            {"account_id": str(credit.id), "debit": "0", "credit": str(amount)},
        ],
    }
    return client.post("/api/cashbook/entries", json=payload, headers=auth_headers(admin))


def _lines(entry):
    return {
        line["account_code"]: (Decimal(line["debit"]), Decimal(line["credit"]))
        for line in entry["lines"]
    }


def _balance(db_session, system_key):
    db_session.expire_all()
    account = (
        db_session.query(models.CashbookAccount)
        .filter(models.CashbookAccount.system_key == system_key)
        .one()
    )
    return cashbook.account_ledger(db_session, account).closing_balance


def _entry_for(db_session, source, source_id=None):
    query = db_session.query(models.CashbookEntry).filter(models.CashbookEntry.source == source)
    if source_id is not None:
        query = query.filter(models.CashbookEntry.source_id == source_id)
    return query.one()


def _make_loan_row(
    db_session,
    member,
    loan_type,
    *,
    principal=Decimal("1000.00"),
    interest=Decimal("0.00"),
    total=None,
    repaid=Decimal("0.00"),
    interest_mode=models.InterestDeductionMode.AT_SOURCE,
    disbursement_date=date(2026, 1, 1),
):
    total = total if total is not None else principal + interest
    loan = models.Loan(
        member_id=member.id,
        loan_type_id=loan_type.id,
        principal=principal,
        interest_amount=interest,
        net_disbursed=principal,
        total_repayable=total,
        monthly_installment=Decimal("100.00"),
        interest_mode=interest_mode,
        disbursement_date=disbursement_date,
        expected_end_date=date(disbursement_date.year + 1, disbursement_date.month, 1),
        amount_repaid=repaid,
        status=models.LoanStatus.ACTIVE,
    )
    db_session.add(loan)
    db_session.commit()
    db_session.refresh(loan)
    return loan


def _credit_savings(db_session, member, amount):
    db_session.add(
        models.SavingsEntry(
            member_id=member.id,
            entry_type=models.SavingsEntryType.CONTRIBUTION,
            amount=Decimal(amount),
            note="Test contribution",
        )
    )
    db_session.commit()


# ---------------------------------------------------------------------------
# Module gate and opening balances
# ---------------------------------------------------------------------------

def test_the_module_toggle_gates_every_route(client, db_session):
    make_settings(db_session, cashbook_module_enabled=False)
    admin = make_admin_user(db_session, username="cb_off", super_admin=True)

    for path in ["/api/cashbook/overview", "/api/cashbook/accounts", "/api/cashbook/entries"]:
        response = client.get(path, headers=auth_headers(admin))
        assert response.status_code == 403, path
        assert "Cashbook module is disabled" in response.json()["detail"], path


def test_nothing_posts_until_the_module_is_enabled(client, db_session):
    """No Settings row means Cashbook is off by default: the route is
    reachable but the service refuses to open the book."""
    _ensure_chart(db_session)
    admin = make_admin_user(db_session, username="cb_default_off", super_admin=True)
    accounts = _accounts(db_session)

    response = client.post(
        "/api/cashbook/opening",
        json={
            "as_of": "2025-12-31",
            "lines": [
                {"account_id": str(accounts[cashbook.BANK].id), "debit": "100.00", "credit": "0"},
                {"account_id": str(accounts[RETAINED].id), "debit": "0", "credit": "100.00"},
            ],
        },
        headers=auth_headers(admin),
    )

    assert response.status_code == 403, response.text
    assert "Cashbook module is disabled" in response.json()["detail"]


def test_activity_is_refused_before_the_opening_journal(client, db_session):
    _enable(db_session)
    _ensure_chart(db_session)
    admin = make_admin_user(db_session, username="cb_unopened", super_admin=True)
    accounts = _accounts(db_session)

    response = _manual(
        client, admin, db_session,
        debit=_account_by_code(db_session, EXPENSE_CODE),
        credit=accounts[cashbook.BANK],
        amount="10.00",
    )

    assert response.status_code == 409, response.text
    assert "Post the opening balances" in response.json()["detail"]


def test_the_opening_journal_can_only_be_posted_once(client, db_session):
    admin = _ready(client, db_session)

    response = client.post(
        "/api/cashbook/opening",
        json=_opening_body(db_session),
        headers=auth_headers(admin),
    )

    assert response.status_code == 409, response.text
    assert "already been posted" in response.json()["detail"]


# ---------------------------------------------------------------------------
# A journal entry must balance
# ---------------------------------------------------------------------------

def test_an_unbalanced_entry_is_rejected(client, db_session):
    admin = _ready(client, db_session)
    accounts = _accounts(db_session)

    response = client.post(
        "/api/cashbook/entries",
        json={
            "entry_date": date.today().isoformat(),
            "narration": "Lopsided",
            "lines": [
                {"account_id": str(accounts[cashbook.BANK].id), "debit": "100.00", "credit": "0"},
                {"account_id": str(accounts[RETAINED].id), "debit": "0", "credit": "90.00"},
            ],
        },
        headers=auth_headers(admin),
    )

    assert response.status_code == 400, response.text
    assert "does not balance" in response.json()["detail"]
    assert db_session.query(models.CashbookEntry).count() == 1  # only the opening


def test_a_line_cannot_carry_both_sides(client, db_session):
    admin = _ready(client, db_session)
    accounts = _accounts(db_session)

    response = client.post(
        "/api/cashbook/entries",
        json={
            "entry_date": date.today().isoformat(),
            "narration": "Two-sided line",
            "lines": [
                {
                    "account_id": str(accounts[cashbook.BANK].id),
                    "debit": "10.00",
                    "credit": "10.00",
                },
                {"account_id": str(accounts[RETAINED].id), "debit": "0", "credit": "0"},
            ],
        },
        headers=auth_headers(admin),
    )

    assert response.status_code == 400, response.text
    assert "one side only" in response.json()["detail"]


# ---------------------------------------------------------------------------
# Chart of accounts
# ---------------------------------------------------------------------------

def test_account_codes_are_unique(client, db_session):
    admin = _ready(client, db_session)

    response = client.post(
        "/api/cashbook/accounts",
        json={"code": "1010", "name": "Second bank", "kind": "asset"},
        headers=auth_headers(admin),
    )

    assert response.status_code == 409, response.text
    assert "already in use" in response.json()["detail"]


def test_system_accounts_cannot_be_deactivated(client, db_session):
    admin = _ready(client, db_session)
    bank = _accounts(db_session)[cashbook.BANK]

    response = client.patch(
        f"/api/cashbook/accounts/{bank.id}",
        json={"is_active": False},
        headers=auth_headers(admin),
    )

    assert response.status_code == 400, response.text
    assert "system account" in response.json()["detail"]


def test_an_account_holding_a_balance_cannot_be_deactivated(client, db_session):
    admin = _ready(client, db_session)
    created = client.post(
        "/api/cashbook/accounts",
        json={"code": "5100", "name": "Stationery", "kind": "expense"},
        headers=auth_headers(admin),
    )
    assert created.status_code == 201, created.text
    stationery = uuid.UUID(created.json()["id"])

    posted = _manual(
        client, admin, db_session,
        debit=_account_by_code(db_session, "5100"),
        credit=_accounts(db_session)[cashbook.BANK],
        amount="40.00",
    )
    assert posted.status_code == 201, posted.text

    response = client.patch(
        f"/api/cashbook/accounts/{stationery}",
        json={"is_active": False},
        headers=auth_headers(admin),
    )

    assert response.status_code == 400, response.text
    assert "still carries a balance" in response.json()["detail"]


def test_accounts_report_balances_on_their_normal_side(client, db_session):
    admin = _ready(client, db_session)

    response = client.get("/api/cashbook/accounts", headers=auth_headers(admin))

    assert response.status_code == 200, response.text
    balances = {row["code"]: Decimal(row["balance"]) for row in response.json()}
    assert balances["1010"] == Decimal("10000.00")  # asset, debit-positive
    assert balances["3000"] == Decimal("10000.00")  # equity, credit-positive


# ---------------------------------------------------------------------------
# Reports
# ---------------------------------------------------------------------------

def test_a_manual_entry_shows_in_the_trial_balance_and_statements(client, db_session):
    admin = _ready(client, db_session)
    response = _manual(
        client, admin, db_session,
        debit=_account_by_code(db_session, EXPENSE_CODE),
        credit=_accounts(db_session)[cashbook.BANK],
        amount="250.00",
    )
    assert response.status_code == 201, response.text

    trial = client.get("/api/cashbook/reports/trial-balance", headers=auth_headers(admin)).json()
    assert trial["balanced"] is True
    assert Decimal(trial["total_debit"]) == Decimal(trial["total_credit"])

    income = client.get(
        "/api/cashbook/reports/income-expenditure", headers=auth_headers(admin)
    ).json()
    assert Decimal(income["total_expenses"]) == Decimal("250.00")
    assert Decimal(income["surplus"]) == Decimal("-250.00")
    assert [row["code"] for row in income["expenses"]] == [EXPENSE_CODE]

    sheet = client.get("/api/cashbook/reports/balance-sheet", headers=auth_headers(admin)).json()
    assert sheet["balanced"] is True
    assert Decimal(sheet["total_assets"]) == Decimal("9750.00")
    assert Decimal(sheet["surplus"]) == Decimal("-250.00")
    assert Decimal(sheet["total_equity"]) == Decimal("9750.00")


def test_the_account_ledger_and_cash_register_track_the_movement(client, db_session):
    admin = _ready(client, db_session)
    assert _manual(
        client, admin, db_session,
        debit=_account_by_code(db_session, EXPENSE_CODE),
        credit=_accounts(db_session)[cashbook.BANK],
        amount="250.00",
    ).status_code == 201
    bank = _accounts(db_session)[cashbook.BANK]

    ledger = client.get(
        f"/api/cashbook/reports/ledger/{bank.id}", headers=auth_headers(admin)
    ).json()
    assert Decimal(ledger["opening_balance"]) == ZERO
    assert Decimal(ledger["closing_balance"]) == Decimal("9750.00")
    assert [Decimal(row["balance"]) for row in ledger["rows"]] == [
        Decimal("10000.00"),
        Decimal("9750.00"),
    ]

    register = client.get("/api/cashbook/reports/cash-register", headers=auth_headers(admin)).json()
    assert [Decimal(row["amount"]) for row in register["rows"]] == [
        Decimal("10000.00"),
        Decimal("-250.00"),
    ]
    assert Decimal(register["bank_balance"]) == Decimal("9750.00")
    assert Decimal(register["cash_balance"]) == ZERO


def test_reversing_an_entry_mirrors_it_and_cannot_repeat(client, db_session):
    admin = _ready(client, db_session)
    entry = _manual(
        client, admin, db_session,
        debit=_account_by_code(db_session, EXPENSE_CODE),
        credit=_accounts(db_session)[cashbook.BANK],
        amount="250.00",
    ).json()

    reversal = client.post(
        f"/api/cashbook/entries/{entry['id']}/reverse",
        json={"reason": "Posted to the wrong account"},
        headers=auth_headers(admin),
    )
    assert reversal.status_code == 201, reversal.text
    body = reversal.json()
    assert body["reverses_entry_id"] == entry["id"]
    assert body["source"] == "reversal"

    mirrored = _lines(body)
    assert mirrored["1010"] == (Decimal("250.00"), ZERO)
    assert mirrored[EXPENSE_CODE] == (ZERO, Decimal("250.00"))
    assert _balance(db_session, cashbook.BANK) == Decimal("10000.00")

    again = client.post(
        f"/api/cashbook/entries/{entry['id']}/reverse",
        json={"reason": "Try again"},
        headers=auth_headers(admin),
    )
    assert again.status_code == 409, again.text
    assert "already been reversed" in again.json()["detail"]


def test_the_overview_reports_the_state_of_the_book(client, db_session):
    admin = _ready(client, db_session)

    response = client.get("/api/cashbook/overview", headers=auth_headers(admin))

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["enabled"] is True
    assert body["opened"] is True
    assert body["opening_date"] == "2025-12-31"
    assert Decimal(body["bank_balance"]) == Decimal("10000.00")
    assert Decimal(body["cash_balance"]) == ZERO
    assert body["entry_count"] == 1
    assert body["current_month_locked"] is False


# ---------------------------------------------------------------------------
# Monthly locks
# ---------------------------------------------------------------------------

def test_a_locked_month_refuses_entries_until_unlocked(client, db_session):
    admin = _ready(client, db_session)
    bank = _accounts(db_session)[cashbook.BANK]
    expense = _account_by_code(db_session, EXPENSE_CODE)

    locked = client.post(
        "/api/cashbook/period-locks",
        json={"period_start": "2026-01-01", "note": "January closed"},
        headers=auth_headers(admin),
    )
    assert locked.status_code == 201, locked.text

    refused = _manual(
        client, admin, db_session,
        debit=expense, credit=bank, amount="15.00", entry_date=date(2026, 1, 15),
    )
    assert refused.status_code == 409, refused.text
    assert "January 2026 is locked" in refused.json()["detail"]

    duplicate = client.post(
        "/api/cashbook/period-locks",
        json={"period_start": "2026-01-01"},
        headers=auth_headers(admin),
    )
    assert duplicate.status_code == 409
    not_first = client.post(
        "/api/cashbook/period-locks",
        json={"period_start": "2025-12-15"},
        headers=auth_headers(admin),
    )
    assert not_first.status_code == 400
    assert "first day" in not_first.json()["detail"]
    future = client.post(
        "/api/cashbook/period-locks",
        json={"period_start": "2099-01-01"},
        headers=auth_headers(admin),
    )
    assert future.status_code == 400
    assert "future month" in future.json()["detail"]

    unlocked = client.delete(
        "/api/cashbook/period-locks/2026-01-01", headers=auth_headers(admin)
    )
    assert unlocked.status_code == 204, unlocked.text

    allowed = _manual(
        client, admin, db_session,
        debit=expense, credit=bank, amount="15.00", entry_date=date(2026, 1, 15),
    )
    assert allowed.status_code == 201, allowed.text


# ---------------------------------------------------------------------------
# Automatic postings
# ---------------------------------------------------------------------------

def _deduction(client, admin, member, loan, *, month=None, loan_amount="500.00"):
    month = month or date.today().strftime("%Y-%m")
    created = client.post(
        "/api/payroll-deductions",
        json={
            "member_id": str(member.id),
            "deduction_month": month,
            "payroll_reference": f"PAY-{month}",
            "lines": [
                {"category": "monthly_contribution", "amount": "2000.00"},
                {"category": "loan_repayment", "loan_id": str(loan.id), "amount": loan_amount},
                {"category": "other", "label": "Welfare", "amount": "100.00"},
            ],
        },
        headers=auth_headers(admin),
    )
    assert created.status_code == 201, created.text
    deduction_id = created.json()["id"]
    assert client.post(
        f"/api/payroll-deductions/{deduction_id}/submit", headers=auth_headers(admin)
    ).status_code == 200
    return deduction_id


def test_confirming_a_deduction_posts_bank_savings_loans_and_other(client, db_session):
    admin = _ready(client, db_session)
    member = make_member(db_session, psn="CB-DED-1", email="cbded1@example.com")
    loan_type = make_loan_type(db_session, "Cashbook Payroll Loan")
    loan = _make_loan_row(db_session, member, loan_type)
    deduction_id = _deduction(client, admin, member, loan)

    confirmed = client.post(
        f"/api/payroll-deductions/{deduction_id}/confirm", headers=auth_headers(admin)
    )
    assert confirmed.status_code == 200, confirmed.text

    entry = _entry_for(db_session, models.CashbookEntrySource.PAYROLL_DEDUCTION, uuid.UUID(deduction_id))
    posted = {
        line.account.system_key or line.account.code: (line.debit, line.credit)
        for line in entry.lines
    }
    assert posted[cashbook.BANK] == (Decimal("2600.00"), ZERO)
    assert posted[cashbook.MEMBER_SAVINGS] == (ZERO, Decimal("2000.00"))
    assert posted[cashbook.LOAN_RECEIVABLE] == (ZERO, Decimal("500.00"))
    assert posted[cashbook.OTHER_DEDUCTIONS_PAYABLE] == (ZERO, Decimal("100.00"))
    assert cashbook.INTEREST_INCOME not in posted  # at-source interest recognised nothing here
    assert entry.source_id == uuid.UUID(deduction_id)
    assert _balance(db_session, cashbook.MEMBER_SAVINGS) == Decimal("2000.00")


def test_spread_interest_is_recognised_as_the_deduction_collects(client, db_session):
    admin = _ready(client, db_session)
    member = make_member(db_session, psn="CB-DED-2", email="cbded2@example.com")
    loan_type = make_loan_type(db_session, "Cashbook Spread Loan")
    loan = _make_loan_row(
        db_session,
        member,
        loan_type,
        interest=Decimal("200.00"),
        total=Decimal("1200.00"),
        interest_mode=models.InterestDeductionMode.SPREAD_OVER_TENURE,
    )
    deduction_id = _deduction(client, admin, member, loan, loan_amount="600.00")

    confirmed = client.post(
        f"/api/payroll-deductions/{deduction_id}/confirm", headers=auth_headers(admin)
    )
    assert confirmed.status_code == 200, confirmed.text

    entry = _entry_for(db_session, models.CashbookEntrySource.PAYROLL_DEDUCTION, uuid.UUID(deduction_id))
    posted = {
        line.account.system_key or line.account.code: (line.debit, line.credit)
        for line in entry.lines
    }
    assert posted[cashbook.LOAN_RECEIVABLE] == (ZERO, Decimal("500.00"))
    assert posted[cashbook.INTEREST_INCOME] == (ZERO, Decimal("100.00"))


def test_voiding_a_confirmed_deduction_reverses_its_journal(client, db_session):
    admin = _ready(client, db_session)
    member = make_member(db_session, psn="CB-DED-3", email="cbded3@example.com")
    loan_type = make_loan_type(db_session, "Cashbook Void Loan")
    loan = _make_loan_row(db_session, member, loan_type)
    deduction_id = _deduction(client, admin, member, loan)
    assert client.post(
        f"/api/payroll-deductions/{deduction_id}/confirm", headers=auth_headers(admin)
    ).status_code == 200

    voided = client.post(
        f"/api/payroll-deductions/{deduction_id}/void",
        json={"reason": "Payroll reversed the remittance"},
        headers=auth_headers(admin),
    )
    assert voided.status_code == 200, voided.text

    original = _entry_for(
        db_session, models.CashbookEntrySource.PAYROLL_DEDUCTION, uuid.UUID(deduction_id)
    )
    reversal = _entry_for(
        db_session, models.CashbookEntrySource.PAYROLL_DEDUCTION_VOID, uuid.UUID(deduction_id)
    )
    assert reversal.reverses_entry_id == original.id
    assert _balance(db_session, cashbook.BANK) == Decimal("10000.00")
    assert _balance(db_session, cashbook.MEMBER_SAVINGS) == ZERO


def test_disbursing_a_loan_posts_the_receivable_the_payout_and_at_source_interest(client, db_session):
    admin = _ready(client, db_session)
    member = make_member(db_session, psn="CB-LOAN-1", email="cbloan1@example.com")
    loan_type = make_loan_type(db_session, "Cashbook Disbursement Loan", interest_rate=Decimal("0.15"))

    response = client.post(
        "/api/loans",
        json={
            "member_id": str(member.id),
            "loan_type_id": str(loan_type.id),
            "principal": "1000.00",
            "disbursement_date": date.today().isoformat(),
        },
        headers=auth_headers(admin),
    )
    assert response.status_code == 201, response.text
    loan_body = response.json()
    assert Decimal(loan_body["interest_amount"]) == Decimal("150.00")

    entry = _entry_for(
        db_session, models.CashbookEntrySource.LOAN_DISBURSEMENT, uuid.UUID(loan_body["id"])
    )
    posted = {
        line.account.system_key or line.account.code: (line.debit, line.credit)
        for line in entry.lines
    }
    assert posted[cashbook.LOAN_RECEIVABLE] == (Decimal("1000.00"), ZERO)
    assert posted[cashbook.BANK] == (ZERO, Decimal("850.00"))
    assert posted[cashbook.INTEREST_INCOME] == (ZERO, Decimal("150.00"))
    assert _balance(db_session, cashbook.BANK) == Decimal("9150.00")


def _submit_repayment(client, member, loan, amount="600.00"):
    response = client.post(
        f"/api/loans/{loan.id}/repayments",
        json={
            "amount_claimed": amount,
            "payment_month": date.today().strftime("%Y-%m"),
            "payment_reference": "TRF-CB-1",
            "receipt_image_base64": "aGVsbG8=",
            "receipt_content_type": "image/png",
        },
        headers=auth_headers(member),
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def test_a_spread_repayment_is_split_between_principal_and_interest(client, db_session):
    admin = _ready(client, db_session)
    member = make_member(db_session, psn="CB-REP-1", email="cbrep1@example.com")
    user = make_member_user(db_session, member)
    loan_type = make_loan_type(db_session, "Cashbook Spread Repayment Loan")
    loan = _make_loan_row(
        db_session,
        member,
        loan_type,
        interest=Decimal("200.00"),
        total=Decimal("1200.00"),
        interest_mode=models.InterestDeductionMode.SPREAD_OVER_TENURE,
    )
    repayment_id = _submit_repayment(client, user, loan)

    verified = client.post(
        f"/api/loan-repayments/{repayment_id}/verify",
        json={"approved": True},
        headers=auth_headers(admin),
    )
    assert verified.status_code == 200, verified.text

    entry = _entry_for(
        db_session, models.CashbookEntrySource.LOAN_REPAYMENT, uuid.UUID(repayment_id)
    )
    posted = {
        line.account.system_key or line.account.code: (line.debit, line.credit)
        for line in entry.lines
    }
    assert posted[cashbook.BANK] == (Decimal("600.00"), ZERO)
    assert posted[cashbook.LOAN_RECEIVABLE] == (ZERO, Decimal("500.00"))
    assert posted[cashbook.INTEREST_INCOME] == (ZERO, Decimal("100.00"))

    db_session.expire_all()
    assert db_session.get(models.Loan, loan.id).amount_repaid == Decimal("600.00")


def test_an_at_source_repayment_is_all_principal(client, db_session):
    admin = _ready(client, db_session)
    member = make_member(db_session, psn="CB-REP-2", email="cbrep2@example.com")
    user = make_member_user(db_session, member)
    loan_type = make_loan_type(db_session, "Cashbook At Source Loan")
    loan = _make_loan_row(
        db_session,
        member,
        loan_type,
        interest=Decimal("150.00"),
        total=Decimal("1000.00"),
        interest_mode=models.InterestDeductionMode.AT_SOURCE,
    )
    repayment_id = _submit_repayment(client, user, loan)

    verified = client.post(
        f"/api/loan-repayments/{repayment_id}/verify",
        json={"approved": True},
        headers=auth_headers(admin),
    )
    assert verified.status_code == 200, verified.text

    entry = _entry_for(
        db_session, models.CashbookEntrySource.LOAN_REPAYMENT, uuid.UUID(repayment_id)
    )
    posted = {line.account.system_key: (line.debit, line.credit) for line in entry.lines}
    assert posted[cashbook.LOAN_RECEIVABLE] == (ZERO, Decimal("600.00"))
    assert cashbook.INTEREST_INCOME not in posted


def test_a_verified_fee_posts_income(client, db_session):
    admin = _ready(client, db_session)
    member = make_member(db_session, psn="CB-FEE-1", email="cbfee1@example.com")
    user = make_member_user(db_session, member)
    loan_type = make_loan_type(
        db_session, "Cashbook Fee Loan", flat_charge=Decimal("50.00")
    )
    loan = _make_loan_row(db_session, member, loan_type)
    loan.fee_amount = Decimal("50.00")
    db_session.commit()

    submitted = client.post(
        f"/api/loans/{loan.id}/fee-payment",
        json={
            "payment_reference": "TRF-FEE-CB",
            "receipt_image_base64": "aGVsbG8=",
            "receipt_content_type": "image/png",
        },
        headers=auth_headers(user),
    )
    assert submitted.status_code == 201, submitted.text
    payment_id = submitted.json()["id"]

    verified = client.post(
        f"/api/loan-fees/{payment_id}/verify",
        json={"approved": True},
        headers=auth_headers(admin),
    )
    assert verified.status_code == 200, verified.text

    entry = _entry_for(db_session, models.CashbookEntrySource.LOAN_FEE, uuid.UUID(payment_id))
    posted = {line.account.system_key: (line.debit, line.credit) for line in entry.lines}
    assert posted[cashbook.BANK] == (Decimal("50.00"), ZERO)
    assert posted[cashbook.LOAN_FEE_INCOME] == (ZERO, Decimal("50.00"))


def test_a_verified_application_fee_posts_once_against_the_application(client, db_session):
    admin = _ready(client, db_session)
    make_settings(db_session, loan_form_fee=Decimal("35.00"))
    member = make_member(db_session, psn="CB-APP-FEE", email="cbappfee@example.com")
    user = make_member_user(db_session, member)
    loan_type = make_loan_type(db_session, "Cashbook Application Fee Loan", open_for_application=True)

    submitted = client.post(
        "/api/loan-applications",
        json={
            "loan_type_id": str(loan_type.id),
            "requested_amount": "500.00",
            "payment_reference": "TRF-APP-CB",
            "receipt_image_base64": "aGVsbG8=",
            "receipt_content_type": "image/png",
        },
        headers=auth_headers(user),
    )
    assert submitted.status_code == 201, submitted.text
    application_id = submitted.json()["id"]
    assert Decimal(submitted.json()["form_fee_amount"]) == Decimal("35.00")

    verified = client.post(
        f"/api/loan-applications/{application_id}/verify-payment",
        json={"approved": True},
        headers=auth_headers(admin),
    )
    assert verified.status_code == 200, verified.text

    entry = _entry_for(
        db_session, models.CashbookEntrySource.LOAN_FEE, uuid.UUID(application_id)
    )
    posted = {line.account.system_key: (line.debit, line.credit) for line in entry.lines}
    assert posted[cashbook.BANK] == (Decimal("35.00"), ZERO)
    assert posted[cashbook.LOAN_FEE_INCOME] == (ZERO, Decimal("35.00"))
    assert _balance(db_session, cashbook.LOAN_FEE_INCOME) == Decimal("35.00")

    repeated = client.post(
        f"/api/loan-applications/{application_id}/verify-payment",
        json={"approved": True},
        headers=auth_headers(admin),
    )
    assert repeated.status_code == 400
    assert (
        db_session.query(models.CashbookEntry)
        .filter(
            models.CashbookEntry.source == models.CashbookEntrySource.LOAN_FEE,
            models.CashbookEntry.source_id == uuid.UUID(application_id),
        )
        .count()
        == 1
    )


def test_application_fee_verification_waits_for_the_opening_journal(client, db_session):
    _enable(db_session)
    _ensure_chart(db_session)
    admin = make_admin_user(db_session, username="cb_app_unopened", super_admin=True)
    make_settings(db_session, loan_form_fee=Decimal("35.00"))
    member = make_member(db_session, psn="CB-APP-UNOPENED", email="cbappunopened@example.com")
    user = make_member_user(db_session, member)
    loan_type = make_loan_type(db_session, "Cashbook Unopened Application", open_for_application=True)

    submitted = client.post(
        "/api/loan-applications",
        json={
            "loan_type_id": str(loan_type.id),
            "requested_amount": "500.00",
            "payment_reference": "TRF-APP-UNOPENED",
            "receipt_image_base64": "aGVsbG8=",
            "receipt_content_type": "image/png",
        },
        headers=auth_headers(user),
    )
    assert submitted.status_code == 201, submitted.text
    application_id = submitted.json()["id"]

    blocked = client.post(
        f"/api/loan-applications/{application_id}/verify-payment",
        json={"approved": True},
        headers=auth_headers(admin),
    )
    assert blocked.status_code == 409, blocked.text
    assert "opening balances" in blocked.json()["detail"]
    db_session.expire_all()
    pending = db_session.query(models.LoanApplication).filter(models.LoanApplication.id == application_id).one()
    assert pending.payment_status == models.PaymentVerificationStatus.AWAITING_VERIFICATION
    assert db_session.query(models.CashbookEntry).count() == 0

    _opening(client, admin, db_session)
    verified = client.post(
        f"/api/loan-applications/{application_id}/verify-payment",
        json={"approved": True},
        headers=auth_headers(admin),
    )
    assert verified.status_code == 200, verified.text
    assert _entry_for(
        db_session, models.CashbookEntrySource.LOAN_FEE, uuid.UUID(application_id)
    )


def test_settlement_and_payout_post_to_the_right_accounts(client, db_session):
    admin = _ready(client, db_session, cash="500.00")
    member = make_member(
        db_session,
        psn="CB-STL-1",
        email="cbstl1@example.com",
        status=models.MemberStatus.NON_FINANCIAL,
        membership_exit_date=date(2026, 10, 31),
        membership_exit_reason="Resigned",
    )
    loan_type = make_loan_type(db_session, "Cashbook Settlement Loan")
    loan = _make_loan_row(
        db_session, member, loan_type, total=Decimal("1000.00"), repaid=Decimal("200.00")
    )
    _credit_savings(db_session, member, "1000.00")

    settled = client.post(
        f"/api/members/{member.id}/settle-exit",
        json={"settled_on": date.today().isoformat()},
        headers=auth_headers(admin),
    )
    assert settled.status_code == 200, settled.text
    settlement = settled.json()
    assert Decimal(settlement["offset_total"]) == Decimal("800.00")
    assert Decimal(settlement["payout_amount"]) == Decimal("200.00")

    entry = _entry_for(
        db_session, models.CashbookEntrySource.SETTLEMENT, uuid.UUID(settlement["id"])
    )
    posted = {line.account.system_key: (line.debit, line.credit) for line in entry.lines}
    assert posted[cashbook.MEMBER_SAVINGS] == (Decimal("1000.00"), ZERO)
    assert posted[cashbook.LOAN_RECEIVABLE] == (ZERO, Decimal("800.00"))
    assert posted[cashbook.PAYOUT_PAYABLE] == (ZERO, Decimal("200.00"))

    paid = client.post(
        f"/api/members/{member.id}/settlements/mark-paid",
        json={"reference": "CASH 0421", "paid_from": "cash"},
        headers=auth_headers(admin),
    )
    assert paid.status_code == 200, paid.text
    assert paid.json()["paid_from"] == "cash"

    payout = _entry_for(
        db_session, models.CashbookEntrySource.SETTLEMENT_PAYOUT, uuid.UUID(settlement["id"])
    )
    payout_lines = {line.account.system_key: (line.debit, line.credit) for line in payout.lines}
    assert payout_lines[cashbook.PAYOUT_PAYABLE] == (Decimal("200.00"), ZERO)
    assert payout_lines[cashbook.CASH] == (ZERO, Decimal("200.00"))
    assert _balance(db_session, cashbook.CASH) == Decimal("300.00")


# ---------------------------------------------------------------------------
# Idempotency and audit
# ---------------------------------------------------------------------------

def test_a_sourced_posting_is_never_duplicated(client, db_session):
    _enable(db_session)
    _ensure_chart(db_session)
    accounts = _accounts(db_session)
    source_id = uuid.uuid4()

    def publish():
        return cashbook.post(
            db_session,
            entry_date=date.today(),
            narration="A repayment the client retried",
            lines=[
                (accounts[cashbook.BANK], Decimal("10.00"), ZERO),
                (accounts[cashbook.LOAN_RECEIVABLE], ZERO, Decimal("10.00")),
            ],
            source=models.CashbookEntrySource.LOAN_REPAYMENT,
            source_id=source_id,
        )

    first = publish()
    db_session.commit()
    second = publish()

    assert second.id == first.id
    assert (
        db_session.query(models.CashbookEntry)
        .filter(models.CashbookEntry.source_id == source_id)
        .count()
        == 1
    )
    assert (
        db_session.query(models.CashbookLine)
        .filter(models.CashbookLine.entry_id == first.id)
        .count()
        == 2
    )


def test_the_cashbook_writes_audit_events(client, db_session):
    admin = _ready(client, db_session)
    entry = _manual(
        client, admin, db_session,
        debit=_account_by_code(db_session, EXPENSE_CODE),
        credit=_accounts(db_session)[cashbook.BANK],
        amount="25.00",
    ).json()
    assert client.post(
        f"/api/cashbook/entries/{entry['id']}/reverse",
        json={"reason": "Duplicate"},
        headers=auth_headers(admin),
    ).status_code == 201
    assert client.post(
        "/api/cashbook/period-locks",
        json={"period_start": "2026-02-01"},
        headers=auth_headers(admin),
    ).status_code == 201

    events = {
        event.event_type
        for event in db_session.query(models.AuditEvent)
        .filter(models.AuditEvent.event_type.like("cashbook.%"))
        .all()
    }
    assert {
        "cashbook.opening_posted",
        "cashbook.entry_posted",
        "cashbook.entry_reversed",
        "cashbook.period_locked",
    } <= events
