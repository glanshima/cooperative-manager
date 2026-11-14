"""
Member names captured as parts (2026-11-14).

Registration sends Last Name, First Name and Other Name(s); the backend
composes the one printed form "Last, First Other(s)" that every screen
reads. Legacy single-field callers keep working, and an edit of any part
recomposes the page-visible name.
"""
from tests.conftest import auth_headers, grant_permission, make_admin_user, make_member


def _officer(db_session, username, *codes):
    admin = make_admin_user(db_session, username=username)
    grant_permission(db_session, admin, *codes)
    return admin


def test_create_composes_the_printed_name(client, db_session, seed_permissions):
    admin = _officer(db_session, "name_create_admin", "member.create")

    res = client.post(
        "/api/members",
        json={
            "psn": "NAME-001",
            "last_name": "Okafor",
            "first_name": "Adaeze",
            "other_names": "Ngozi Chika",
            "next_of_kin_is_member": False,
        },
        headers=auth_headers(admin),
    )

    assert res.status_code == 201
    body = res.json()
    assert body["name"] == "Okafor, Adaeze Ngozi Chika"
    assert body["last_name"] == "Okafor"
    assert body["first_name"] == "Adaeze"
    assert body["other_names"] == "Ngozi Chika"


def test_other_names_are_optional(client, db_session, seed_permissions):
    admin = _officer(db_session, "name_optional_admin", "member.create")

    res = client.post(
        "/api/members",
        json={
            "psn": "NAME-002",
            "last_name": "Bello",
            "first_name": "Fatima",
            "next_of_kin_is_member": False,
        },
        headers=auth_headers(admin),
    )

    assert res.status_code == 201
    assert res.json()["name"] == "Bello, Fatima"
    assert res.json()["other_names"] is None


def test_create_still_accepts_a_legacy_single_name(client, db_session, seed_permissions):
    admin = _officer(db_session, "name_legacy_admin", "member.create")

    res = client.post(
        "/api/members",
        json={"psn": "NAME-003", "name": "Legacy Import", "next_of_kin_is_member": False},
        headers=auth_headers(admin),
    )

    assert res.status_code == 201
    assert res.json()["name"] == "Legacy Import"


def test_create_without_any_name_is_rejected(client, db_session, seed_permissions):
    admin = _officer(db_session, "name_missing_admin", "member.create")

    res = client.post(
        "/api/members",
        json={"psn": "NAME-004", "next_of_kin_is_member": False},
        headers=auth_headers(admin),
    )

    assert res.status_code == 422


def test_search_matches_the_old_given_name_first_order(client, db_session, seed_permissions):
    admin = _officer(db_session, "name_search_admin", "member.view", "member.create")

    created = client.post(
        "/api/members",
        json={
            "psn": "NAME-006",
            "last_name": "Adeyemi",
            "first_name": "Ngozi",
            "other_names": "Funke",
            "next_of_kin_is_member": False,
        },
        headers=auth_headers(admin),
    )
    assert created.status_code == 201

    for term in ("Adeyemi", "Ngozi", "Ngozi Adeyemi", "Funke"):
        res = client.get("/api/members", params={"search": term}, headers=auth_headers(admin))
        assert res.status_code == 200
        psns = {m["psn"] for m in res.json()["items"]}
        assert "NAME-006" in psns, f"{term!r} did not find the member"


def test_updating_a_part_recomposes_the_printed_name(client, db_session, seed_permissions):
    admin = _officer(db_session, "name_update_admin", "member.update")
    member = make_member(db_session, psn="NAME-007", name="Ada Obi")
    member.first_name = "Ada"
    member.last_name = "Obi"
    db_session.commit()

    res = client.put(
        f"/api/members/{member.id}",
        json={"other_names": "Ngozi Chika"},
        headers=auth_headers(admin),
    )

    assert res.status_code == 200
    assert res.json()["name"] == "Obi, Ada Ngozi Chika"

    cleared = client.put(
        f"/api/members/{member.id}",
        json={"other_names": None},
        headers=auth_headers(admin),
    )
    assert cleared.status_code == 200
    assert cleared.json()["name"] == "Obi, Ada"


def test_update_cannot_drop_the_family_name(client, db_session, seed_permissions):
    admin = _officer(db_session, "name_update_guard_admin", "member.update")
    member = make_member(db_session, psn="NAME-008", name="Ada Obi")
    member.first_name = "Ada"
    member.last_name = "Obi"
    db_session.commit()

    res = client.put(
        f"/api/members/{member.id}",
        json={"last_name": ""},
        headers=auth_headers(admin),
    )

    assert res.status_code == 422
