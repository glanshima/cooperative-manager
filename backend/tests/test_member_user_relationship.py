"""Regression test for the Phase 0 assessment finding, and its own
hotfix: Member.user used to be a single uselist=False relationship
that would raise when both a member-role and admin-role User referenced
the same member_id at once. The first fix attempt (a custom-primaryjoin
relationship, 2026-08-30) could not be verified in the sandbox it was
built in (no SQLAlchemy available) and broke mapper configuration in
production, taking down unrelated endpoints (including login). Reverted
to plain query methods (get_member_login_user / get_admin_login_user)
instead -- no relationship() at all, so there is nothing for mapper
configuration to get wrong; these only run an explicit query when
actually called."""
from tests.conftest import make_admin_user, make_member, make_member_user


def test_member_with_only_a_self_service_login(db_session, seed_permissions):
    member = make_member(db_session, psn="REL-001", email="rel1@example.com")
    login = make_member_user(db_session, member)

    assert member.get_member_login_user(db_session).id == login.id
    assert member.get_admin_login_user(db_session) is None


def test_member_with_only_an_admin_link(db_session, seed_permissions):
    member = make_member(db_session, psn="REL-002", email="rel2@example.com")
    admin = make_admin_user(db_session, username="rel_admin_2", member_id=member.id)

    assert member.get_admin_login_user(db_session).id == admin.id
    assert member.get_member_login_user(db_session) is None


def test_member_with_both_a_self_service_login_and_an_admin_link(db_session, seed_permissions):
    """This is the exact scenario that used to crash: both a member-role
    and an admin-role User referencing the same member_id at once (an
    EXCO officer who is also a self-service member, e.g. glanshima)."""
    member = make_member(db_session, psn="REL-003", email="rel3@example.com")
    member_login = make_member_user(db_session, member)
    admin_login = make_admin_user(db_session, username="rel_admin_3", member_id=member.id)

    # The old single `member.user` attribute no longer exists at all --
    # this confirms nobody can accidentally reintroduce a call to it.
    assert not hasattr(member, "user")

    fetched_member_login = member.get_member_login_user(db_session)
    fetched_admin_login = member.get_admin_login_user(db_session)
    assert fetched_member_login.id == member_login.id
    assert fetched_admin_login.id == admin_login.id
    assert fetched_member_login.id != fetched_admin_login.id


def test_member_with_no_login_at_all(db_session, seed_permissions):
    member = make_member(db_session, psn="REL-004", email="rel4@example.com")
    assert member.get_member_login_user(db_session) is None
    assert member.get_admin_login_user(db_session) is None
