"""Universal fee and staged review, approval and disbursement rules."""
from datetime import date
from decimal import Decimal

from sqlalchemy import event

from app import cashbook, models
from tests.conftest import (
    auth_headers,
    make_admin_user,
    make_loan_type,
    make_member,
    make_member_user,
    make_settings,
)


def _fixture(db_session, psn):
    make_settings(db_session, loan_form_fee=Decimal("40.00"))
    member = make_member(db_session, psn=psn, email=f"{psn.lower()}@example.com")
    user = make_member_user(db_session, member)
    loan_type = make_loan_type(
        db_session,
        f"Workflow Loan {psn}",
        interest_rate=Decimal("0.10"),
        tenure_months=12,
        flat_charge=Decimal("1.00"),
        interest_mode=models.InterestDeductionMode.SPREAD_FIRST_MONTHS,
        interest_spread_months=3,
        open_for_application=True,
    )
    admin = make_admin_user(db_session, username=f"workflow_{psn.lower()}", super_admin=True)
    return member, user, loan_type, admin


def _ready_cashbook(db_session, admin):
    make_settings(db_session, cashbook_module_enabled=True)
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
        ("3000", "Retained earnings", models.CashbookAccountKind.EQUITY, "RETAINED_EARNINGS"),
        ("4000", "Loan interest income", models.CashbookAccountKind.INCOME, cashbook.INTEREST_INCOME),
        ("4010", "Loan fee income", models.CashbookAccountKind.INCOME, cashbook.LOAN_FEE_INCOME),
    ]
    existing = {account.code for account in db_session.query(models.CashbookAccount).all()}
    for code, name, kind, system_key in chart:
        if code not in existing:
            db_session.add(
                models.CashbookAccount(code=code, name=name, kind=kind, system_key=system_key)
            )
    db_session.commit()
    accounts = {
        account.system_key: account
        for account in db_session.query(models.CashbookAccount)
        .filter(models.CashbookAccount.system_key.isnot(None))
        .all()
    }
    cashbook.post_opening(
        db_session,
        as_of=date(2025, 12, 31),
        lines=[
            (accounts[cashbook.BANK], Decimal("10000.00"), Decimal("0.00")),
            (accounts["RETAINED_EARNINGS"], Decimal("0.00"), Decimal("10000.00")),
        ],
        actor_id=admin.id,
    )
    db_session.commit()


def _submit(client, user, loan_type):
    response = client.post(
        "/api/loan-applications",
        json={
            "loan_type_id": str(loan_type.id),
            "requested_amount": "1000.00",
            "requested_tenure_months": 6,
            "payment_reference": "TRF-WORKFLOW",
            "receipt_image_base64": "aGVsbG8=",
            "receipt_content_type": "image/png",
        },
        headers=auth_headers(user),
    )
    assert response.status_code == 201, response.text
    return response.json()


def _verify_payment(client, admin, application_id):
    response = client.post(
        f"/api/loan-applications/{application_id}/verify-payment",
        json={"approved": True},
        headers=auth_headers(admin),
    )
    assert response.status_code == 200, response.text
    return response.json()


def _decide(client, admin, application_id):
    response = client.post(
        f"/api/loan-applications/{application_id}/decide",
        json={
            "approved": True,
            "approved_amount": "1000.00",
            "approved_tenure_months": 6,
        },
        headers=auth_headers(admin),
    )
    assert response.status_code == 200, response.text
    return response.json()


def _disburse(client, admin, application_id):
    response = client.post(
        f"/api/loan-applications/{application_id}/disburse",
        json={},
        headers=auth_headers(admin),
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_application_snapshots_the_universal_fee_and_uses_frozen_approval_terms(
    client, db_session
):
    _, user, loan_type, admin = _fixture(db_session, "PSN-WORKFLOW-1")
    submitted = _submit(client, user, loan_type)
    application_id = submitted["id"]
    assert Decimal(submitted["form_fee_amount"]) == Decimal("40.00")

    make_settings(db_session, loan_form_fee=Decimal("75.00"))
    snapshot = client.get(
        f"/api/loan-applications/{application_id}", headers=auth_headers(user)
    ).json()
    assert Decimal(snapshot["form_fee_amount"]) == Decimal("40.00")

    blocked_decision = client.post(
        f"/api/loan-applications/{application_id}/decide",
        json={
            "approved": True,
            "approved_amount": "1000.00",
            "approved_tenure_months": 6,
        },
        headers=auth_headers(admin),
    )
    assert blocked_decision.status_code == 400
    assert "payment must be verified" in blocked_decision.json()["detail"]

    _ready_cashbook(db_session, admin)
    _verify_payment(client, admin, application_id)
    blocked_disbursement = client.post(
        f"/api/loan-applications/{application_id}/disburse",
        json={},
        headers=auth_headers(admin),
    )
    assert blocked_disbursement.status_code == 400
    assert "Only approved applications" in blocked_disbursement.json()["detail"]

    approved = _decide(client, admin, application_id)
    assert approved["resulting_loan_id"] is None
    assert Decimal(approved["approved_interest_rate"]) == Decimal("0.1000")
    assert approved["approved_interest_mode"] == "spread_first_months"
    assert approved["approved_interest_spread_months"] == 3
    assert Decimal(approved["form_fee_amount"]) == Decimal("40.00")

    db_session.add(
        models.LoanTypeRateVersion(
            loan_type_id=loan_type.id,
            interest_rate=Decimal("0.25"),
            tenure_months=12,
            flat_charge=Decimal("99.00"),
            interest_mode=models.InterestDeductionMode.AT_SOURCE,
            effective_from=date.today().replace(day=1),
        )
    )
    db_session.commit()

    disbursed = _disburse(client, admin, application_id)
    loan_id = disbursed["resulting_loan_id"]
    loan_response = client.get(f"/api/loans/{loan_id}", headers=auth_headers(user))
    assert loan_response.status_code == 200, loan_response.text
    loan = loan_response.json()
    assert Decimal(loan["interest_amount"]) == Decimal("100.00")
    assert Decimal(loan["net_disbursed"]) == Decimal("1000.00")
    assert Decimal(loan["total_repayable"]) == Decimal("1100.00")
    assert Decimal(loan["monthly_installment"]) == Decimal("166.67")
    assert Decimal(loan["interest_installment"]) == Decimal("33.33")
    assert loan["interest_mode"] == "spread_first_months"
    assert loan["interest_spread_months"] == 3
    assert Decimal(loan["fee_amount"]) == Decimal("40.00")
    assert loan["fee_status"] == "paid"

    duplicate = client.post(
        f"/api/loans/{loan_id}/fee-payment",
        json={
            "payment_reference": "TRF-SECOND-FEE",
            "receipt_image_base64": "aGVsbG8=",
            "receipt_content_type": "image/png",
        },
        headers=auth_headers(user),
    )
    assert duplicate.status_code == 400
    assert "paid with its application" in duplicate.json()["detail"]
    assert (
        db_session.query(models.LoanFeePayment)
        .filter(models.LoanFeePayment.loan_id == loan_id)
        .count()
        == 0
    )


def test_approval_resolves_all_terms_from_one_locked_configuration_snapshot(
    client, db_session
):
    _, user, loan_type, admin = _fixture(db_session, "PSN-WORKFLOW-LOCKED")
    submitted = _submit(client, user, loan_type)
    _ready_cashbook(db_session, admin)
    _verify_payment(client, admin, submitted["id"])
    statements = []

    def capture_sql(conn, cursor, statement, parameters, context, executemany):
        statements.append(" ".join(statement.upper().split()))

    bind = db_session.get_bind()
    event.listen(bind, "before_cursor_execute", capture_sql)
    try:
        approved = _decide(client, admin, submitted["id"])
    finally:
        event.remove(bind, "before_cursor_execute", capture_sql)

    rate_queries = [
        statement for statement in statements if "FROM LOAN_TYPE_RATE_VERSIONS" in statement
    ]
    assert len(rate_queries) == 1
    assert "FOR UPDATE" in rate_queries[0]
    assert any(
        "FROM SETTINGS" in statement and "FOR UPDATE" in statement
        for statement in statements
    )
    assert any(
        "FROM LOAN_TYPES" in statement and "FOR UPDATE" in statement
        for statement in statements
    )
    assert Decimal(approved["approved_interest_rate"]) == Decimal("0.1000")
    assert approved["approved_interest_mode"] == "spread_first_months"
    assert approved["approved_interest_spread_months"] == 3


def test_legacy_approved_application_without_frozen_terms_uses_disbursement_terms(
    client, db_session
):
    member, user, loan_type, admin = _fixture(db_session, "PSN-WORKFLOW-2")
    application = models.LoanApplication(
        member_id=member.id,
        loan_type_id=loan_type.id,
        requested_amount=Decimal("1000.00"),
        approved_amount=Decimal("1000.00"),
        approved_tenure_months=6,
        form_fee_amount=Decimal("40.00"),
        payment_reference="TRF-LEGACY",
        receipt_image_base64="aGVsbG8=",
        receipt_content_type="image/png",
        payment_status=models.PaymentVerificationStatus.VERIFIED,
        status=models.LoanApplicationStatus.APPROVED,
    )
    db_session.add(application)
    db_session.commit()
    db_session.refresh(application)

    db_session.add(
        models.LoanTypeRateVersion(
            loan_type_id=loan_type.id,
            interest_rate=Decimal("0.25"),
            tenure_months=12,
            flat_charge=Decimal("99.00"),
            interest_mode=models.InterestDeductionMode.SPREAD_OVER_TENURE,
            effective_from=date.today().replace(day=1),
        )
    )
    db_session.commit()

    disbursed = _disburse(client, admin, application.id)
    loan_response = client.get(
        f"/api/loans/{disbursed['resulting_loan_id']}", headers=auth_headers(user)
    )
    assert loan_response.status_code == 200, loan_response.text
    loan = loan_response.json()
    assert Decimal(loan["interest_amount"]) == Decimal("250.00")
    assert Decimal(loan["net_disbursed"]) == Decimal("1000.00")
    assert Decimal(loan["total_repayable"]) == Decimal("1250.00")
    assert loan["interest_mode"] == "spread_over_tenure"
    assert Decimal(loan["fee_amount"]) == Decimal("40.00")
    assert loan["fee_status"] == "paid"
