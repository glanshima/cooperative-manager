"""Regression test for the Phase 0 assessment finding: Member.user used
to be a single uselist=False relationship that would raise when both a
member-role and admin-role User referenced the same member_id at once.
Split into Member.member_login_user / Member.admin_login_user."""
from tests.conftest import make_admin_user, make_member, make_member_user


def test_member_with_only_a_self_service_login(db_session, seed_permissions):
    member = make_member(db_session, psn="REL-001", email="rel1@example.com")
    login = make_member_user(db_session, member)

    db_session.refresh(member)
    assert member.member_login_user is not None
    assert member.member_login_user.id == login.id
    assert member.admin_login_user is None


def test_member_with_only_an_admin_link(db_session, seed_permissions):
    member = make_member(db_session, psn="REL-002", email="rel2@example.com")
    admin = make_admin_user(db_session, username="rel_admin_2", member_id=member.id)

    db_session.refresh(member)
    assert member.admin_login_user is not None
    assert member.admin_login_user.id == admin.id
    assert member.member_login_user is None


def test_member_with_both_a_self_service_login_and_an_admin_link(client, db_session, seed_permissions):
    """This is the exact scenario that used to crash: both a member-role
    and an admin-role User referencing the same member_id at once (an
    EXCO officer who is also a self-service member)."""
    member = make_member(db_session, psn="REL-003", email="rel3@example.com")
    member_login = make_member_user(db_session, member)
    admin_login = make_admin_user(db_session, username="rel_admin_3", member_id=member.id)

    db_session.refresh(member)
    # The old single `member.user` attribute no longer exists at all --
    # this would be an AttributeError if it were still there, which is
    # itself part of confirming the fix (nobody can accidentally
    # reintroduce a call to it).
    assert not hasattr(member, "user")

    assert member.member_login_user is not None
    assert member.member_login_user.id == member_login.id
    assert member.admin_login_user is not None
    assert member.admin_login_user.id == admin_login.id
    assert member.member_login_user.id != member.admin_login_user.id
