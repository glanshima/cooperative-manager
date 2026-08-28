"""
Guards against permission-catalogue drift (Phase 1 remediation).

permissions_catalogue.py's module docstring has claimed since Phase 1
that "every permission code referenced anywhere in the backend ... MUST
appear in PERMISSION_CATALOGUE. This is enforced by ...
tests/test_permission_catalogue.py" -- but this file didn't actually
exist yet, so that claim was false. This test makes it true: it greps
the router source for every string literal passed to require_permission
(...)/require_any_permission(...)/user_has_permission(db, user, ...) and
asserts each one is a real catalogue entry, so a typo'd or renamed
permission code fails CI instead of silently 403-ing everyone (or, worse,
silently granting access to nobody's role and going unnoticed) in
production.
"""
import re
from pathlib import Path

from app.permissions_catalogue import PERMISSION_CATALOGUE, PERMISSION_CODES

ROUTERS_DIR = Path(__file__).resolve().parent.parent / "app" / "routers"

# Matches: require_permission("code"), require_any_permission("a", "b"),
# and user_has_permission(db, user, "code") -- capturing every quoted
# permission-code-looking literal (category.action) passed to any of
# them.
_CALL_PATTERN = re.compile(
    r"(?:require_permission|require_any_permission|user_has_permission)\(([^)]*)\)"
)
_STRING_LITERAL_PATTERN = re.compile(r'"([a-z_]+\.[a-z_]+)"')


def _referenced_permission_codes() -> set:
    codes = set()
    for path in ROUTERS_DIR.glob("*.py"):
        text = path.read_text()
        for call_args in _CALL_PATTERN.findall(text):
            codes.update(_STRING_LITERAL_PATTERN.findall(call_args))
    return codes


def test_catalogue_has_no_duplicate_codes():
    codes = [code for code, _, _ in PERMISSION_CATALOGUE]
    assert len(codes) == len(set(codes)), "Duplicate permission code in PERMISSION_CATALOGUE"


def test_every_referenced_permission_code_is_in_the_catalogue():
    referenced = _referenced_permission_codes()
    assert referenced, "Expected to find at least one require_permission(...) call in routers/"
    unknown = referenced - PERMISSION_CODES
    assert not unknown, (
        f"Router code references permission code(s) not present in "
        f"PERMISSION_CATALOGUE: {sorted(unknown)}. Either add them to the "
        f"catalogue or fix the typo."
    )


def test_dynamically_selected_decision_permissions_are_in_the_catalogue():
    """loan_applications.py::decide_application picks between
    'loan.approve' and 'loan.reject' at runtime (a variable, not a string
    literal, is passed to user_has_permission), so the static scan above
    can't see them. Pin them here explicitly instead."""
    assert {"loan.approve", "loan.reject"} <= PERMISSION_CODES


def test_every_default_role_permission_is_in_the_catalogue():
    from app.permissions_catalogue import DEFAULT_ROLES

    for role_name, spec in DEFAULT_ROLES.items():
        unknown = set(spec["permissions"]) - PERMISSION_CODES
        assert not unknown, f"Default role {role_name!r} grants unknown code(s): {sorted(unknown)}"
