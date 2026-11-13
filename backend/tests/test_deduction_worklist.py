"""The payroll entry worklist (2026-11).

An officer should not pick members out of a dropdown and guess amounts.
The worklist answers "who is still owed an entry for this month, and what
does the server expect?" so the queue shrinks as it is worked through.

  - a member appears only when something is due: a contribution, a loan
    instalment, or a financial member with no amount on file (which the
    officer must resolve rather than skip silently);
  - entering a member moves them out of the pending queue, and entry_state
    chooses which queue the response lists;
  - the queue is paginated like the ledger, but due_count, pending_count,
    entered_count and expected_total always describe the whole month -- a
    page of the queue cannot add up to the month;
  - amounts, arrears and warnings come from the expectation engine;
  - conflicted members stay visible and flagged (the read policy);
  - the endpoint needs deduction.view and the Deductions module.
"""
from datetime import date
from decimal import Decimal

from sqlalchemy import event

from app import models
from tests.conftest import (
    auth_headers,
    grant_permission,
    make_admin_user,
    make_loan_type,
    make_member,
)

MONTH = "2026-11"


def _financial(db_session, psn, *, amount="5000.00"):
    return make_member(
        db_session,
        psn=psn,
        name=f"Member {psn}",
        monthly_contribution_amount=Decimal(amount) if amount else None,
        contribution_effective_from=date(2026, 1, 1) if amount else None,
    )


def _loan(db_session, member, loan_type, *, repaid="0.00"):
    loan = models.Loan(
        member_id=member.id,
        loan_type_id=loan_type.id,
        principal=Decimal("1200.00"),
        interest_amount=Decimal("0.00"),
        net_disbursed=Decimal("1200.00"),
        total_repayable=Decimal("1200.00"),
        monthly_installment=Decimal("100.00"),
        disbursement_date=date(2026, 1, 1),
        expected_end_date=date(2027, 1, 1),
        amount_repaid=Decimal(repaid),
        status=models.LoanStatus.ACTIVE,
    )
    db_session.add(loan)
    db_session.commit()
    db_session.refresh(loan)
    return loan


def _worklist(client, user, *, month=MONTH, entry_state=None, skip=None, limit=None):
    params = {"month": month}
    if entry_state is not None:
        params["entry_state"] = entry_state
    if skip is not None:
        params["skip"] = skip
    if limit is not None:
        params["limit"] = limit
    return client.get(
        "/api/payroll-deductions/worklist",
        headers=auth_headers(user),
        params=params,
    )


def _selects_during(db_session, call):
    """The SELECT statements issued while `call` runs. Statements rather
    than timing, because the worklist's cost is the point: pricing every
    member separately is invisible on a five-member month and ruinous on a
    190-member one."""
    statements = []
    engine = db_session.get_bind()

    def collect(conn, cursor, statement, parameters, context, executemany):
        if statement.lstrip().upper().startswith("SELECT"):
            statements.append(statement)

    event.listen(engine, "before_cursor_execute", collect)
    try:
        call()
    finally:
        event.remove(engine, "before_cursor_execute", collect)
    return statements


def _enter(client, admin, member, loan=None):
    lines = [{"category": "monthly_contribution", "amount": "5000.00"}]
    if loan is not None:
        lines.append({"category": "loan_repayment", "loan_id": str(loan.id), "amount": "100.00"})
    response = client.post(
        "/api/payroll-deductions",
        headers=auth_headers(admin),
        json={"member_id": str(member.id), "deduction_month": MONTH, "lines": lines},
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_the_queue_lists_members_who_owe_something_with_expected_amounts(client, db_session):
    admin = make_admin_user(db_session, username="worklist_admin", super_admin=True)
    member = _financial(db_session, "PSN-WL-1")
    loan_type = make_loan_type(db_session, "Worklist Loan")
    loan = _loan(db_session, member, loan_type, repaid="1000.00")

    response = _worklist(client, admin)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["month"] == "2026-11-01"
    assert body["due_count"] == 1
    assert body["entered_count"] == 0
    assert body["expected_total"] == "5100.00"
    item = body["items"][0]
    assert item["member_id"] == str(member.id)
    assert item["due_reasons"] == ["contribution", "loan_instalment"]
    assert item["expected_total"] == "5100.00"
    assert item["deduction_id"] is None
    amounts = {line["category"]: line["amount"] for line in item["lines"]}
    assert amounts == {"monthly_contribution": "5000.00", "loan_repayment": "100.00"}
    assert any(line["loan_id"] == str(loan.id) for line in item["lines"])


def test_entering_a_member_removes_them_from_the_queue(client, db_session):
    admin = make_admin_user(db_session, username="worklist_admin", super_admin=True)
    member = _financial(db_session, "PSN-WL-2")
    other = _financial(db_session, "PSN-WL-3")

    before = _worklist(client, admin).json()
    assert {item["member_id"] for item in before["items"]} == {str(member.id), str(other.id)}

    record = _enter(client, admin, member)

    after = _worklist(client, admin).json()
    assert [item["member_id"] for item in after["items"]] == [str(other.id)]
    assert after["due_count"] == 2
    assert after["pending_count"] == 1
    assert after["entered_count"] == 1
    assert after["expected_total"] == "5000.00"

    entered_segment = _worklist(client, admin, entry_state="entered").json()
    assert entered_segment["total"] == 1
    item = entered_segment["items"][0]
    assert item["member_id"] == str(member.id)
    assert item["deduction_id"] == record["id"]
    assert item["deduction_status"] == "draft"

    both = _worklist(client, admin, entry_state="all").json()
    assert {item["member_id"] for item in both["items"]} == {str(member.id), str(other.id)}
    assert both["total"] == 2
    # The month's money is the pending half, whichever segment is open.
    assert both["expected_total"] == "5000.00"
    assert after["pending_count"] + after["entered_count"] == after["due_count"]


def test_voiding_a_record_returns_the_member_to_the_queue(client, db_session):
    admin = make_admin_user(db_session, username="worklist_admin", super_admin=True)
    member = _financial(db_session, "PSN-WL-4")
    record = _enter(client, admin, member)
    assert _worklist(client, admin).json()["items"] == []

    response = client.post(
        "/api/payroll-deductions/bulk/void",
        headers=auth_headers(admin),
        json={"ids": [record["id"]], "reason": "Entered against the wrong month"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["results"][0]["ok"] is True

    assert [item["member_id"] for item in _worklist(client, admin).json()["items"]] == [
        str(member.id)
    ]


def test_a_financial_member_without_an_amount_is_listed_for_resolution(client, db_session):
    admin = make_admin_user(db_session, username="worklist_admin", super_admin=True)
    member = _financial(db_session, "PSN-WL-5", amount=None)

    item = _worklist(client, admin).json()["items"][0]

    assert item["member_id"] == str(member.id)
    assert item["due_reasons"] == ["contribution_amount_missing"]
    assert item["lines"] == []
    assert item["expected_total"] == "0.00"
    assert item["warnings"]


def test_members_with_nothing_due_are_left_out(client, db_session):
    admin = make_admin_user(db_session, username="worklist_admin", super_admin=True)
    make_member(
        db_session,
        psn="PSN-WL-6",
        status=models.MemberStatus.NON_FINANCIAL,
    )

    assert _worklist(client, admin).json()["items"] == []


def test_an_exited_member_with_a_loan_is_listed_with_the_exit_date(client, db_session):
    admin = make_admin_user(db_session, username="worklist_admin", super_admin=True)
    member = make_member(
        db_session,
        psn="PSN-WL-7",
        status=models.MemberStatus.NON_FINANCIAL,
        membership_exit_date=date(2026, 9, 15),
        membership_exit_reason="Left the service",
    )
    loan_type = make_loan_type(db_session, "Worklist Loan")
    _loan(db_session, member, loan_type, repaid="1000.00")

    item = _worklist(client, admin).json()["items"][0]

    assert item["member_status"] == "non_financial"
    assert item["membership_exit_date"] == "2026-09-15"
    assert item["due_reasons"] == ["loan_instalment"]
    assert item["expected_total"] == "100.00"


def test_arrears_arrive_as_their_own_line_in_the_expected_total(client, db_session):
    admin = make_admin_user(db_session, username="worklist_admin", super_admin=True)
    member = _financial(db_session, "PSN-WL-8", amount=None)
    loan_type = make_loan_type(db_session, "Worklist Loan")
    _loan(db_session, member, loan_type, repaid="300.00")

    item = _worklist(client, admin).json()["items"][0]

    instalment, arrears = item["lines"]
    assert instalment["category"] == "loan_repayment"
    assert instalment["amount"] == "100.00"
    assert arrears["category"] == "loan_arrears"
    assert arrears["amount"] == "600.00"
    assert arrears["months_behind"] == 6
    # The catch-up is money payroll should actually take, so it is in the
    # month's expected total rather than only noted beside the instalment.
    assert item["expected_total"] == "700.00"
    # The missing contribution amount is a warning of its own, and this
    # member is due for both the instalment and the catch-up.
    assert item["due_reasons"] == [
        "contribution_amount_missing",
        "loan_instalment",
        "loan_arrears",
    ]


def test_a_conflicted_member_stays_visible_and_flagged(client, db_session):
    officer = make_admin_user(db_session, username="worklist_conflicted", super_admin=True)
    linked = make_member(db_session, psn="PSN-WL-9")
    officer.member_id = linked.id
    db_session.commit()
    member = _financial(db_session, "PSN-WL-10")
    db_session.add(
        models.MemberRelationship(
            member_id=member.id,
            related_member_id=linked.id,
            conflict_of_interest=True,
            status=models.RelationshipStatus.ACTIVE,
        )
    )
    db_session.commit()

    body = _worklist(client, officer).json()

    flagged = next(item for item in body["items"] if item["member_id"] == str(member.id))
    assert flagged["conflicted"] is True
    assert all(
        item["conflicted"] is False for item in body["items"] if item["member_id"] != str(member.id)
    )


def test_the_worklist_needs_the_view_permission(client, db_session, seed_permissions):
    viewer = make_admin_user(db_session, username="worklist_viewer")
    grant_permission(db_session, viewer, "deduction.view")
    assert _worklist(client, viewer).status_code == 200

    outsider = make_admin_user(db_session, username="worklist_outsider")
    grant_permission(db_session, outsider, "deduction.create")
    assert _worklist(client, outsider).status_code == 403


def test_the_worklist_validates_the_month(client, db_session):
    admin = make_admin_user(db_session, username="worklist_admin", super_admin=True)

    assert _worklist(client, admin, month="2026-13").status_code == 422
    assert _worklist(client, admin, month="November").status_code == 422


def test_the_deductions_toggle_gates_the_worklist(client, db_session):
    admin = make_admin_user(db_session, username="worklist_admin", super_admin=True)
    settings = db_session.query(models.Settings).first()
    if settings is None:
        settings = models.Settings()
        db_session.add(settings)
    settings.deductions_module_enabled = False
    db_session.commit()

    response = _worklist(client, admin)

    assert response.status_code == 403
    assert "disabled" in response.json()["detail"]


def test_the_queue_pages_but_its_totals_stay_month_wide(client, db_session):
    admin = make_admin_user(db_session, username="worklist_admin", super_admin=True)
    members = [_financial(db_session, f"PSN-WL-P{i:02d}") for i in range(25)]
    assert len({member.name for member in members}) == 25

    first = _worklist(client, admin).json()

    assert first["skip"] == 0
    assert first["limit"] == 20
    assert first["total"] == 25 == len(first["items"]) + 5
    assert len(first["items"]) == 20
    # Month-wide, not page-scoped: 25 members at 5,000 each.
    assert first["due_count"] == 25
    assert first["pending_count"] == 25
    assert first["expected_total"] == "125000.00"

    second = _worklist(client, admin, skip=20).json()

    assert len(second["items"]) == 5
    assert second["total"] == 25
    assert second["due_count"] == 25
    assert second["expected_total"] == "125000.00"
    # Page 2 continues where page 1 stopped instead of repeating it, and the
    # whole month walks in name order.
    names = [item["member_name"] for item in first["items"] + second["items"]]
    assert len({name for name in names}) == 25
    assert names == sorted(names)
    page_one = {item["member_id"] for item in first["items"]}
    assert {item["member_id"] for item in second["items"]}.isdisjoint(page_one)
    assert page_one | {item["member_id"] for item in second["items"]} == {
        str(member.id) for member in members
    }


def test_the_officer_chooses_how_many_rows_a_page_holds(client, db_session):
    admin = make_admin_user(db_session, username="worklist_admin", super_admin=True)
    _financial(db_session, "PSN-WL-S1")
    _financial(db_session, "PSN-WL-S2")
    _financial(db_session, "PSN-WL-S3")

    body = _worklist(client, admin, limit=2).json()

    assert body["limit"] == 2
    assert len(body["items"]) == 2
    assert body["total"] == 3
    assert body["pending_count"] == 3
    assert body["expected_total"] == "15000.00"


def test_the_queue_rejects_a_page_that_cannot_be_served(client, db_session):
    admin = make_admin_user(db_session, username="worklist_admin", super_admin=True)
    _financial(db_session, "PSN-WL-B1")

    assert _worklist(client, admin, limit=0).status_code == 422
    assert _worklist(client, admin, limit=101).status_code == 422
    assert _worklist(client, admin, skip=-1).status_code == 422
    assert _worklist(client, admin, entry_state="unfinished").status_code == 422
    # A skip past the last page is empty, not an error: the officer can be
    # paging while the queue shrinks under them.
    assert _worklist(client, admin, skip=50).json()["items"] == []


def test_a_record_for_a_member_nothing_now_expects_is_not_counted_as_entered(
    client, db_session
):
    """`entered_count` answers 'how much of this month's queue is done', so
    it counts entered members who are still due. A record whose expectation
    has since disappeared (a loan repaid by bank in the meantime) stays in
    the ledger, which is the complete record list, rather than inflating the
    queue's progress."""
    admin = make_admin_user(db_session, username="worklist_admin", super_admin=True)
    due = _financial(db_session, "PSN-WL-E1")
    settled = make_member(
        db_session, psn="PSN-WL-E2", status=models.MemberStatus.NON_FINANCIAL
    )
    loan_type = make_loan_type(db_session, "Worklist Loan")
    loan = _loan(db_session, settled, loan_type)
    response = client.post(
        "/api/payroll-deductions",
        headers=auth_headers(admin),
        json={
            "member_id": str(settled.id),
            "deduction_month": MONTH,
            "lines": [{"category": "loan_repayment", "loan_id": str(loan.id), "amount": "100.00"}],
        },
    )
    assert response.status_code == 201, response.text

    db_session.get(models.Loan, loan.id).amount_repaid = Decimal("1200.00")
    db_session.commit()

    body = _worklist(client, admin, entry_state="all").json()

    assert body["due_count"] == 1
    assert body["pending_count"] == 1
    assert body["entered_count"] == 0
    assert [item["member_id"] for item in body["items"]] == [str(due.id)]


def test_pricing_a_bigger_month_does_not_cost_more_queries(client, db_session):
    """The queue prices the whole month on every call because its counts are
    month-wide, so pricing has to run in batches: one loan query and two
    repayment queries per month, not per member."""
    admin = make_admin_user(db_session, username="worklist_admin", super_admin=True)
    for index in range(5):
        member = _financial(db_session, f"PSN-WL-N{index}")
        _loan(db_session, member, make_loan_type(db_session, f"Worklist Loan {index}"))

    small = _selects_during(db_session, lambda: _worklist(client, admin).json())
    for index in range(5, 15):
        member = _financial(db_session, f"PSN-WL-N{index}")
        _loan(db_session, member, make_loan_type(db_session, f"Worklist Loan {index}"))
    large = _selects_during(db_session, lambda: _worklist(client, admin).json())

    assert _worklist(client, admin).json()["due_count"] == 15
    # Three times the members and loans, the same number of queries.
    assert len(large) == len(small)
    # ...and well clear of a query per member, which would be 45+ here.
    assert len(small) < 20