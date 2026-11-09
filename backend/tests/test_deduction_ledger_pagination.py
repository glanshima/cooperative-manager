"""A paginated ledger, and a submit-all that is scoped in the database.

Both changes answer the same defect: the ledger used to return one array,
so a month of deductions rendered as an endless scroll and "submit all"
could only ever mean "submit the rows this page happens to have loaded".

  - GET /api/payroll-deductions returns {items, total, skip, limit}. `total`
    counts the FULL filtered set, because the page controls and the
    submit-all preview need that number rather than len(items).
  - GET /api/payroll-deductions/submittable-ids decides the batch from the
    database and separates drafts with no lines, which submit rejects,
    instead of letting them fail inside a batch and look like breakage.
  - Bulk actions accept at most 100 ids: every record in a batch commits on
    its own (the audit write inside the loop commits), so an unbounded
    request that outlives the deployment's function timeout would leave a
    half-applied month with no per-item report.
"""
from datetime import date
import uuid

from app import models
from tests.conftest import (
    auth_headers,
    grant_permission,
    make_admin_user,
    make_member,
)

MONTH = "2026-11"
OTHER_MONTH = "2026-10"


def _member(db_session, psn):
    return make_member(db_session, psn=psn, name=f"Member {psn}", email=f"{psn.lower()}@example.com")


def _draft(client, admin, member, *, month=MONTH, amount="2000.00"):
    res = client.post(
        "/api/payroll-deductions",
        headers=auth_headers(admin),
        json={
            "member_id": str(member.id),
            "deduction_month": month,
            "lines": [{"category": "monthly_contribution", "amount": amount}],
        },
    )
    assert res.status_code == 201, res.text
    return res.json()


def _draft_with_no_lines(db_session, member, *, month=MONTH):
    """Created in the database because the API requires at least one line --
    a draft abandoned mid-entry still exists, and submit-all has to account
    for it honestly."""
    deduction = models.PayrollDeduction(
        member_id=member.id,
        deduction_month=date.fromisoformat(f"{month}-01"),
        status=models.PayrollDeductionStatus.DRAFT,
    )
    db_session.add(deduction)
    db_session.commit()
    db_session.refresh(deduction)
    return str(deduction.id)


def _post(client, admin, path, **kwargs):
    return client.post(path, headers=auth_headers(admin), **kwargs)


def _ledger(client, admin, **params):
    return client.get("/api/payroll-deductions", headers=auth_headers(admin), params=params)


def test_the_ledger_returns_a_page_and_the_size_of_the_whole_set(client, db_session):
    admin = make_admin_user(db_session, username="page_admin", super_admin=True)
    ids = [
        _draft(client, admin, _member(db_session, f"PSN-PG-{n}"))["id"] for n in range(1, 4)
    ]

    first = _ledger(client, admin, month=MONTH, limit=2)
    assert first.status_code == 200, first.text
    body = first.json()
    assert body["total"] == 3
    assert [record["id"] for record in body["items"]] == ids[:2]
    assert (body["skip"], body["limit"]) == (0, 2)

    second = _ledger(client, admin, month=MONTH, limit=2, skip=2)
    assert second.json()["total"] == 3
    assert [record["id"] for record in second.json()["items"]] == ids[2:]

    # The default page is what the ledger UI asks for, and it is echoed back
    # so the client never has to duplicate the constant.
    assert _ledger(client, admin, month=MONTH).json()["limit"] == 50


def test_total_follows_the_filters_not_the_page(client, db_session):
    admin = make_admin_user(db_session, username="page_filter", super_admin=True)
    member_a = _member(db_session, "PSN-PG-10")
    member_b = _member(db_session, "PSN-PG-11")
    _draft(client, admin, member_a)
    _draft(client, admin, member_b)
    _draft(client, admin, member_a, month=OTHER_MONTH)

    assert _ledger(client, admin, month=MONTH, limit=1).json()["total"] == 2
    assert _ledger(client, admin, limit=1).json()["total"] == 3
    assert _ledger(client, admin, member_id=str(member_a.id), limit=1).json()["total"] == 2


def test_void_records_count_only_when_they_are_the_filter(client, db_session):
    admin = make_admin_user(db_session, username="page_void", super_admin=True)
    kept = _draft(client, admin, _member(db_session, "PSN-PG-12"))
    dropped = _draft(client, admin, _member(db_session, "PSN-PG-13"))
    _post(client, admin, f"/api/payroll-deductions/{dropped['id']}/void", json={"reason": "re-enter"})

    assert _ledger(client, admin, month=MONTH).json()["total"] == 1
    voided = _ledger(client, admin, month=MONTH, status="void")
    assert voided.json()["total"] == 1
    assert [record["id"] for record in voided.json()["items"]] == [dropped["id"]]


def test_page_bounds_are_rejected_before_the_query(client, db_session):
    admin = make_admin_user(db_session, username="page_bounds", super_admin=True)

    assert _ledger(client, admin, limit=0).status_code == 422
    assert _ledger(client, admin, limit=201).status_code == 422
    assert _ledger(client, admin, skip=-1).status_code == 422


def test_the_scope_endpoint_reads_a_static_path_not_an_id(client, db_session):
    """/submittable-ids must win against /{deduction_id}, which would
    otherwise answer 422 'invalid uuid' for a batch preview."""
    admin = make_admin_user(db_session, username="scope_route", super_admin=True)
    res = client.get(
        "/api/payroll-deductions/submittable-ids",
        params={"month": MONTH},
        headers=auth_headers(admin),
    )
    assert res.status_code == 200, res.text
    assert res.json() == {"month": f"{MONTH}-01", "ids": [], "empty_draft_ids": []}


def test_submit_all_scope_covers_drafts_with_lines_only(client, db_session):
    admin = make_admin_user(db_session, username="scope_drafts", super_admin=True)

    submittable = _draft(client, admin, _member(db_session, "PSN-SC-1"))["id"]
    empty = _draft_with_no_lines(db_session, _member(db_session, "PSN-SC-2"))
    other_month = _draft(client, admin, _member(db_session, "PSN-SC-3"), month=OTHER_MONTH)["id"]

    already_sent = _draft(client, admin, _member(db_session, "PSN-SC-4"))["id"]
    _post(client, admin, f"/api/payroll-deductions/{already_sent}/submit")

    voided = _draft(client, admin, _member(db_session, "PSN-SC-5"))["id"]
    _post(client, admin, f"/api/payroll-deductions/{voided}/void", json={"reason": "wrong member"})

    res = client.get(
        "/api/payroll-deductions/submittable-ids",
        params={"month": MONTH},
        headers=auth_headers(admin),
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["ids"] == [submittable]
    assert body["empty_draft_ids"] == [empty]
    assert other_month not in body["ids"] + body["empty_draft_ids"]
    assert already_sent not in body["ids"] + body["empty_draft_ids"]
    assert voided not in body["ids"] + body["empty_draft_ids"]


def test_the_scope_prediction_is_what_bulk_submit_actually_accepts(client, db_session):
    admin = make_admin_user(db_session, username="scope_predict", super_admin=True)
    submittable = _draft(client, admin, _member(db_session, "PSN-SC-10"))["id"]
    empty = _draft_with_no_lines(db_session, _member(db_session, "PSN-SC-11"))

    scope = client.get(
        "/api/payroll-deductions/submittable-ids",
        params={"month": MONTH},
        headers=auth_headers(admin),
    ).json()

    accepted = _post(
        client, admin, "/api/payroll-deductions/bulk/submit", json={"ids": scope["ids"]}
    )
    assert accepted.status_code == 200, accepted.text
    assert all(result["ok"] for result in accepted.json()["results"])

    refused = _post(
        client, admin, "/api/payroll-deductions/bulk/submit", json={"ids": scope["empty_draft_ids"]}
    )
    assert refused.status_code == 200, refused.text
    results = {result["id"]: result for result in refused.json()["results"]}
    assert results[empty]["ok"] is False
    assert submittable not in results


def test_the_scope_endpoint_needs_the_submit_permission(client, db_session, seed_permissions):
    viewer = make_admin_user(db_session, username="scope_viewer")
    grant_permission(db_session, viewer, "deduction.view")
    sender = make_admin_user(db_session, username="scope_sender")
    grant_permission(db_session, sender, "deduction.submit")

    res = client.get(
        "/api/payroll-deductions/submittable-ids",
        params={"month": MONTH},
        headers=auth_headers(viewer),
    )
    assert res.status_code == 403, res.text

    res = client.get(
        "/api/payroll-deductions/submittable-ids",
        params={"month": MONTH},
        headers=auth_headers(sender),
    )
    assert res.status_code == 200, res.text


def test_bulk_actions_cap_the_batch_size(client, db_session):
    admin = make_admin_user(db_session, username="bulk_cap", super_admin=True)
    too_many = [str(uuid.uuid4()) for _ in range(101)]

    res = _post(
        client, admin, "/api/payroll-deductions/bulk/submit", json={"ids": too_many}
    )
    assert res.status_code == 422, res.text

    # At the cap the request is accepted and every record is reported --
    # missing rows fail individually rather than aborting the batch.
    res = _post(client, admin, "/api/payroll-deductions/bulk/submit", json={"ids": too_many[:100]})
    assert res.status_code == 200, res.text
    results = res.json()["results"]
    assert len(results) == 100
    assert not any(result["ok"] for result in results)

    assert _post(
        client, admin, "/api/payroll-deductions/bulk/submit", json={"ids": []}
    ).status_code == 422
