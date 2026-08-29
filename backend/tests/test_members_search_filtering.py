"""
Members Search & Filtering Remediation tests. Covers independent
filters, filter combination, search+filter combination, whitespace
normalization, pagination-with-total-count, no-match state, and the
filter-options endpoint.
"""
from tests.conftest import auth_headers, grant_permission, make_admin_user, make_member


def _viewer(db_session, username="msf_admin"):
    admin = make_admin_user(db_session, username=username)
    grant_permission(db_session, admin, "member.view")
    return admin


# ---------------------------------------------------------------------------
# Independent filters (filter_fix.md Section 1 / Test 1-4)
# ---------------------------------------------------------------------------

def test_bank_filter_alone_no_search_needed(client, db_session, seed_permissions):
    make_member(db_session, psn="MSF-001", email="msf1@example.com", bank_name="Bank A", department="Accounts")
    make_member(db_session, psn="MSF-002", email="msf2@example.com", bank_name="Bank B", department="Accounts")
    admin = _viewer(db_session, "msf_admin_bank")

    res = client.get("/api/members", params={"bank_name": "Bank A"}, headers=auth_headers(admin))
    assert res.status_code == 200
    body = res.json()
    assert body["total"] == 1
    assert all(m["bank_name"] == "Bank A" for m in body["items"])


def test_department_filter_alone_no_search_needed(client, db_session, seed_permissions):
    make_member(db_session, psn="MSF-003", email="msf3@example.com", department="Accounts")
    make_member(db_session, psn="MSF-004", email="msf4@example.com", department="Logistics")
    admin = _viewer(db_session, "msf_admin_dept")

    res = client.get("/api/members", params={"department": "Accounts"}, headers=auth_headers(admin))
    body = res.json()
    assert body["total"] == 1
    assert body["items"][0]["department"] == "Accounts"


def test_status_filter_alone_no_search_needed(client, db_session, seed_permissions):
    from app import models

    make_member(db_session, psn="MSF-005", email="msf5@example.com", status=models.MemberStatus.FINANCIAL)
    make_member(db_session, psn="MSF-006", email="msf6@example.com", status=models.MemberStatus.NON_FINANCIAL)
    admin = _viewer(db_session, "msf_admin_status")

    res = client.get("/api/members", params={"status": "financial"}, headers=auth_headers(admin))
    body = res.json()
    assert body["total"] == 1
    assert body["items"][0]["status"] == "financial"


# ---------------------------------------------------------------------------
# Filters combine with AND (filter_fix.md Section 3, Tests 5-7)
# ---------------------------------------------------------------------------

def test_bank_and_department_combine(client, db_session, seed_permissions):
    make_member(db_session, psn="MSF-007", email="msf7@example.com", bank_name="Bank A", department="Accounts")
    make_member(db_session, psn="MSF-008", email="msf8@example.com", bank_name="Bank A", department="Logistics")
    make_member(db_session, psn="MSF-009", email="msf9@example.com", bank_name="Bank B", department="Accounts")
    admin = _viewer(db_session, "msf_admin_combo1")

    res = client.get(
        "/api/members",
        params={"bank_name": "Bank A", "department": "Accounts"},
        headers=auth_headers(admin),
    )
    body = res.json()
    assert body["total"] == 1
    assert body["items"][0]["psn"] == "MSF-007"


def test_bank_department_and_status_combine(client, db_session, seed_permissions):
    from app import models

    make_member(
        db_session, psn="MSF-010", email="msf10@example.com", bank_name="Bank A",
        department="Accounts", status=models.MemberStatus.FINANCIAL,
    )
    make_member(
        db_session, psn="MSF-011", email="msf11@example.com", bank_name="Bank A",
        department="Accounts", status=models.MemberStatus.NON_FINANCIAL,
    )
    admin = _viewer(db_session, "msf_admin_combo2")

    res = client.get(
        "/api/members",
        params={"bank_name": "Bank A", "department": "Accounts", "status": "financial"},
        headers=auth_headers(admin),
    )
    body = res.json()
    assert body["total"] == 1
    assert body["items"][0]["psn"] == "MSF-010"


# ---------------------------------------------------------------------------
# Search + filters combine (filter_fix.md Section 4, Test 8)
# ---------------------------------------------------------------------------

def test_search_combines_with_all_filters(client, db_session, seed_permissions):
    from app import models

    make_member(
        db_session, psn="MSF-012", name="John Adeyemi", email="msf12@example.com",
        bank_name="Bank A", department="Accounts", status=models.MemberStatus.FINANCIAL,
    )
    # Same name, wrong bank -- must be excluded.
    make_member(
        db_session, psn="MSF-013", name="John Okafor", email="msf13@example.com",
        bank_name="Bank B", department="Accounts", status=models.MemberStatus.FINANCIAL,
    )
    admin = _viewer(db_session, "msf_admin_search_combo")

    res = client.get(
        "/api/members",
        params={"search": "John", "bank_name": "Bank A", "department": "Accounts", "status": "financial"},
        headers=auth_headers(admin),
    )
    body = res.json()
    assert body["total"] == 1
    assert body["items"][0]["psn"] == "MSF-012"


# ---------------------------------------------------------------------------
# Search fields: member number/PSN, name, phone (with whitespace)
# ---------------------------------------------------------------------------

def test_search_matches_psn_name_and_phone(client, db_session, seed_permissions):
    make_member(db_session, psn="32074", name="Someone Specific", email="msf14@example.com", phone="08012345678")
    admin = _viewer(db_session, "msf_admin_fields")

    for query in ["32074", "Someone Specific", "08012345678"]:
        res = client.get("/api/members", params={"search": query}, headers=auth_headers(admin))
        assert res.json()["total"] == 1, f"search {query!r} should match"


def test_search_whitespace_normalization_matches_member_32074_style_case(client, db_session, seed_permissions):
    """Regression case per the addendum: leading/trailing whitespace
    around a search term must not change the result."""
    make_member(db_session, psn="32074", name="Regression Case", email="msf15@example.com")
    admin = _viewer(db_session, "msf_admin_ws")

    for query in ["32074", " 32074", "32074 ", " 32074 "]:
        res = client.get("/api/members", params={"search": query}, headers=auth_headers(admin))
        assert res.json()["total"] == 1, f"search {query!r} should match after normalization"


def test_search_preserves_internal_spaces(client, db_session, seed_permissions):
    make_member(db_session, psn="MSF-016", name="John Doe", email="msf16@example.com")
    admin = _viewer(db_session, "msf_admin_internal_space")

    res = client.get("/api/members", params={"search": "John Doe"}, headers=auth_headers(admin))
    assert res.json()["total"] == 1
    # "JohnDoe" (internal space removed) must NOT match -- proves internal
    # whitespace isn't being collapsed/stripped.
    res2 = client.get("/api/members", params={"search": "JohnDoe"}, headers=auth_headers(admin))
    assert res2.json()["total"] == 0


def test_whitespace_only_search_is_treated_as_no_search(client, db_session, seed_permissions):
    make_member(db_session, psn="MSF-017", email="msf17@example.com")
    make_member(db_session, psn="MSF-018", email="msf18@example.com")
    admin = _viewer(db_session, "msf_admin_blank")

    res = client.get("/api/members", params={"search": "   "}, headers=auth_headers(admin))
    assert res.json()["total"] == 2


# ---------------------------------------------------------------------------
# No-match state (Section 9 / 11)
# ---------------------------------------------------------------------------

def test_no_match_returns_empty_items_not_an_error(client, db_session, seed_permissions):
    make_member(db_session, psn="MSF-019", email="msf19@example.com")
    admin = _viewer(db_session, "msf_admin_nomatch")

    res = client.get("/api/members", params={"search": "NONEXISTENTMEMBER999"}, headers=auth_headers(admin))
    assert res.status_code == 200
    body = res.json()
    assert body["items"] == []
    assert body["total"] == 0


# ---------------------------------------------------------------------------
# Pagination total count (Section 2 / 7)
# ---------------------------------------------------------------------------

def test_pagination_total_reflects_full_filtered_dataset_not_just_page(client, db_session, seed_permissions):
    for i in range(30):
        make_member(db_session, psn=f"MSF-PAGE-{i:03d}", email=f"msf-page-{i}@example.com", department="Accounts")
    admin = _viewer(db_session, "msf_admin_paging")

    res = client.get(
        "/api/members",
        params={"department": "Accounts", "skip": 0, "limit": 10},
        headers=auth_headers(admin),
    )
    body = res.json()
    assert len(body["items"]) == 10
    assert body["total"] == 30, "total must reflect the full filtered dataset, not just this page"


# ---------------------------------------------------------------------------
# Filter options endpoint (Section 14)
# ---------------------------------------------------------------------------

def test_filter_options_reflects_actual_distinct_data(client, db_session, seed_permissions):
    make_member(db_session, psn="MSF-020", email="msf20@example.com", bank_name="Bank X", department="Legal")
    make_member(db_session, psn="MSF-021", email="msf21@example.com", bank_name="Bank X", department="Legal")
    make_member(db_session, psn="MSF-022", email="msf22@example.com", bank_name="Bank Y", department="HR")
    admin = _viewer(db_session, "msf_admin_options")

    res = client.get("/api/members/filter-options", headers=auth_headers(admin))
    assert res.status_code == 200
    body = res.json()
    assert set(body["banks"]) == {"Bank X", "Bank Y"}
    assert set(body["departments"]) == {"Legal", "HR"}


def test_filter_options_requires_member_view_permission(client, db_session, seed_permissions):
    admin = make_admin_user(db_session, username="msf_admin_no_perm")
    res = client.get("/api/members/filter-options", headers=auth_headers(admin))
    assert res.status_code == 403
