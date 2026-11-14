"""
Seeds the LOCAL OFFLINE SANDBOX with sample data: permissions/roles
authoritative catalogue, a super-admin login, sample members (+ a
member-to-member next-of-kin link), sample loan types with rate
versions, two member logins (one normal, one forcing the first-login
password reset flow), a member-linked admin fixture for the smoke test's
Next-of-Kin conflict check, and 26 login-less members owing a
contribution so the payroll deduction Enter queue runs past one page,
plus one login-less member whose loan is behind schedule so the queue
pre-fills an arrears catch-up line.

THIS SCRIPT IS LOCAL-ONLY. It refuses to run unless DATABASE_URL points
at the sandbox Postgres (127.0.0.1:55432, see scripts/local_db.py).
Sample data must never be pushed to Neon/production -- only code travels.

Safe to re-run: every entity is looked up by its natural key first and
skipped if it already exists.

Usage (from the repo root):
    DATABASE_URL="postgresql://postgres:@127.0.0.1:55432/mact_local" \
        backend/.venv/Scripts/python.exe scripts/seed_local_sample_data.py

The same command works after starting the sandbox with:
    backend/.venv/Scripts/python.exe scripts/local_db.py start
"""
import os
import sys
from datetime import date
from decimal import Decimal
from urllib.parse import urlparse

import dotenv

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(ROOT, "backend"))
sys.path.insert(0, SCRIPTS_DIR)

# Load backend/.env for SECRET_KEY (imported by app.auth); an explicitly
# set env var always wins (override=False), so DATABASE_URL below is the
# one the caller passed in, not whatever .env happens to say.
dotenv.load_dotenv(os.path.join(ROOT, "backend", ".env"), override=False)

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise SystemExit(
        "Set DATABASE_URL before running this script, e.g.\n"
        '  DATABASE_URL="postgresql://postgres:@127.0.0.1:55432/mact_local" '
        "python scripts/seed_local_sample_data.py"
    )

SANDBOX_HOSTS = {"127.0.0.1", "localhost"}
SANDBOX_PORT = 55432

_parsed = urlparse(DATABASE_URL)
if _parsed.hostname not in SANDBOX_HOSTS or _parsed.port != SANDBOX_PORT:
    raise SystemExit(
        f"REFUSING TO RUN: DATABASE_URL does not point at the local sandbox "
        f"(expected host in {sorted(SANDBOX_HOSTS)} and port {SANDBOX_PORT}, "
        f"got {_parsed.hostname}:{_parsed.port}).\n"
        "This seed creates sample data that must never reach Neon/production. "
        "Start the sandbox first: python scripts/local_db.py start"
    )

from sqlalchemy import create_engine, select  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app.account_lifecycle import validate_password_strength  # noqa: E402
from app.validation import compose_member_name  # noqa: E402
from app.auth import hash_password  # noqa: E402
from app.loan_calc import compute_expected_end_date  # noqa: E402
from app.models import (  # noqa: E402
    AccountStatus,
    Gender,
    Loan,
    LoanStatus,
    LoanType,
    LoanTypeRateVersion,
    Member,
    MemberRelationship,
    MemberStatus,
    RelationshipStatus,
    RelationshipType,
    User,
    UserRole,
)

import seed_permissions  # noqa: E402

engine = create_engine(DATABASE_URL)
Session = sessionmaker(bind=engine)

ADMIN_USERNAME = "localadmin"
ADMIN_PASSWORD = "LocalAdmin#2026"
MEMBER_PASSWORD = "MemberTest#2026"

# Fixture for scripts/smoke_test.py's opt-in Next-of-Kin conflict check:
# an admin account linked to its own Member, whose Next of Kin is
# MCT-0001. The fixture member has no login; it exists only to give the
# admin a linked member so the conflict guard treats MCT-0001 as
# off-limits.
SMOKE_NOK_ADMIN_USERNAME = "smoke_nok_admin"
SMOKE_NOK_ADMIN_PASSWORD = "SmokeNok#2026"
SMOKE_NOK_FIXTURE_PSN = "MCT-9001"

# Fixture for the deductions Enter queue. The queue pages at 20, so 26
# financial members each owing a contribution make two pages with a short
# second one -- the only way paging, the Pending/Entered/All segment counts
# and the rows-per-page choice show any behaviour worth checking by hand.
# With 20 or fewer due members the whole queue is one page and every control
# looks correct while doing nothing.
QUEUE_FIXTURE_COUNT = 26
QUEUE_FIXTURE_PSN_PREFIX = "QLPAGE"
QUEUE_FIXTURE_CONTRIBUTION = Decimal("5000.00")
QUEUE_FIXTURE_EFFECTIVE_FROM = date(2026, 1, 1)

# Fixture for the arrears (catch-up) deduction line. A loan taken in July is
# four months into its schedule by November: one instalment is due for this
# month and the three earlier ones are owed. The expectation engine therefore
# pre-fills TWO lines for the one loan -- the instalment and a catch-up --
# which is the only shape that shows the split arrears maths, the per-loan
# balance cap and the schedule's Arrears column doing anything.
ARREARS_FIXTURE_PSN = "QLARREARS"
ARREARS_FIXTURE_DISBURSED = date(2026, 7, 1)
ARREARS_FIXTURE_TENURE_MONTHS = 6
ARREARS_FIXTURE_INSTALLMENT = Decimal("10000.00")
# Interest-at-source: the repayable total is the principal, so the numbers
# below stay readable (6 x 10,000 = 60,000).
ARREARS_FIXTURE_PRINCIPAL = ARREARS_FIXTURE_INSTALLMENT * ARREARS_FIXTURE_TENURE_MONTHS

SAMPLE_MEMBERS = [
    # (psn, name, gender, department, phone, email, status, bank, account_no,
    #  next_of_kin, nok_phone, loan_restricted, restriction_reason)
    ("MCT-0001", "Adaeze Okafor", Gender.FEMALE, "Accounts", "0803 111 0001",
     "adaeze.okafor@example.com", MemberStatus.FINANCIAL, "GTBank", "0123456789",
     "Emeka Nwosu (member, see linked relationship)", "0803 111 0002", False, None),
    ("MCT-0002", "Emeka Nwosu", Gender.MALE, "Operations", "0803 111 0002",
     "emeka.nwosu@example.com", MemberStatus.FINANCIAL, "Zenith Bank", "0234567891",
     None, None, False, None),
    ("MCT-0003", "Fatima Bello", Gender.FEMALE, "Audit", "0803 111 0003",
     "fatima.bello@example.com", MemberStatus.NON_FINANCIAL, "Access Bank", "0345678912",
     None, None, False, None),
    ("MCT-0004", "Chukwuemeka Eze", Gender.MALE, "ICT", "0803 111 0004",
     "chukwuemeka.eze@example.com", MemberStatus.FINANCIAL, "UBA", "0456789123",
     None, None, True, "Sample: already repaying 3 active loans"),
    ("MCT-0005", "Ngozi Adeyemi", Gender.FEMALE, "Treasury", "0803 111 0005",
     "ngozi.adeyemi@example.com", MemberStatus.FINANCIAL, "First Bank", "0567891234",
     None, None, False, None),
    ("MCT-0006", "Ibrahim Musa", Gender.MALE, "Stores", "0803 111 0006",
     "ibrahim.musa@example.com", MemberStatus.FINANCIAL, "Stanbic IBTC", "0678912345",
     None, None, False, None),
]

# name, description, interest_rate, tenure_months, flat_charge, open_for_application
SAMPLE_LOAN_TYPES = [
    ("Capital Loan", "Long-tenure capital project loan", 0.1500, 12, 0, True),
    ("Short Loan", "Short-tenure emergency loan", 0.0800, 3, 0, True),
    ("Quick Loan", "Quick-access loan with processing charge", 0.1000, 6, 500, True),
    ("Item Loan", "Purchase-of-item loan (staff-disbursed only)", 0.0500, 9, 500, False),
]
RATE_EFFECTIVE_FROM = date(2026, 1, 1)


def _split_full_name(full_name: str) -> tuple[str, str, str | None]:
    """The sample list is written given-name-first ("Adaeze Okafor"); store
    it the way the app prints it, with the family name separate."""
    parts = full_name.split()
    if len(parts) == 1:
        return parts[0], "", None
    return parts[-1], parts[0], " ".join(parts[1:-1]) or None


def seed_members(session):
    created = 0
    for (psn, name, gender, department, phone, email, status, bank, account_no,
         nok, nok_phone, restricted, restriction_reason) in SAMPLE_MEMBERS:
        if session.execute(select(Member).where(Member.psn == psn)).scalar_one_or_none():
            continue
        last_name, first_name, other_names = _split_full_name(name)
        session.add(Member(
            psn=psn, name=compose_member_name(last_name, first_name, other_names),
            first_name=first_name, last_name=last_name, other_names=other_names,
            gender=gender, department=department, phone=phone,
            email=email, status=status, bank_name=bank, account_number=account_no,
            next_of_kin=nok, next_of_kin_phone=nok_phone,
            loan_restricted=restricted, restriction_reason=restriction_reason,
        ))
        created += 1
    session.flush()
    print(f"Members: {created} created, {len(SAMPLE_MEMBERS) - created} already existed.")


def seed_relationship(session):
    """MCT-0001's Next of Kin is MCT-0002 (both members)."""
    a = session.execute(select(Member).where(Member.psn == "MCT-0001")).scalar_one_or_none()
    b = session.execute(select(Member).where(Member.psn == "MCT-0002")).scalar_one_or_none()
    if not a or not b:
        return
    existing = session.execute(
        select(MemberRelationship).where(
            MemberRelationship.member_id == a.id,
            MemberRelationship.related_member_id == b.id,
            MemberRelationship.relationship_type == RelationshipType.NEXT_OF_KIN,
            MemberRelationship.status == RelationshipStatus.ACTIVE,
        )
    ).scalar_one_or_none()
    if existing:
        print("Member relationship MCT-0001 -> MCT-0002 (NOK): already exists.")
        return
    session.add(MemberRelationship(
        member_id=a.id, related_member_id=b.id,
        relationship_type=RelationshipType.NEXT_OF_KIN,
        status=RelationshipStatus.ACTIVE,
    ))
    print("Member relationship MCT-0001 -> MCT-0002 (NOK): created.")


def seed_conflict_fixture(session):
    """
    Admin account linked to a fixture member whose Next of Kin is
    MCT-0001. This is what lets scripts/smoke_test.py prove -- against a
    live server -- that a conflicted officer cannot list, read, or update
    that member, while an unconflicted admin still can.

    The fixture admin is a super admin on purpose: is_super_admin is
    explicitly NOT an escape hatch for conflict enforcement, so this
    exercises the guard at its strongest permission level. Idempotent;
    re-running repairs a missing link rather than duplicating anything.
    """
    actor = session.execute(select(Member).where(Member.psn == "MCT-0001")).scalar_one()

    fixture = session.execute(
        select(Member).where(Member.psn == SMOKE_NOK_FIXTURE_PSN)
    ).scalar_one_or_none()
    if fixture is None:
        fixture = Member(
            psn=SMOKE_NOK_FIXTURE_PSN,
            name=compose_member_name("Fixture", "Smoke", "NOK"),
            first_name="Smoke",
            last_name="Fixture",
            other_names="NOK",
            status=MemberStatus.NON_FINANCIAL,
        )
        session.add(fixture)
        session.flush()
        print(f"Member {SMOKE_NOK_FIXTURE_PSN} (smoke conflict fixture): created.")
    else:
        # The fixture predates split names; the seed owns its own fixtures,
        # so bring an existing row onto the composed-name form too.
        if fixture.first_name != "Smoke" or fixture.last_name != "Fixture":
            fixture.first_name, fixture.last_name, fixture.other_names = "Smoke", "Fixture", "NOK"
            fixture.name = compose_member_name("Fixture", "Smoke", "NOK")
        print(f"Member {SMOKE_NOK_FIXTURE_PSN} (smoke conflict fixture): already exists.")

    relationship = session.execute(
        select(MemberRelationship).where(
            MemberRelationship.member_id == fixture.id,
            MemberRelationship.related_member_id == actor.id,
            MemberRelationship.relationship_type == RelationshipType.NEXT_OF_KIN,
            MemberRelationship.status == RelationshipStatus.ACTIVE,
        )
    ).scalar_one_or_none()
    if relationship is None:
        session.add(MemberRelationship(
            member_id=fixture.id, related_member_id=actor.id,
            relationship_type=RelationshipType.NEXT_OF_KIN,
            status=RelationshipStatus.ACTIVE,
            conflict_of_interest=True,
        ))
        print(f"Member relationship {SMOKE_NOK_FIXTURE_PSN} -> MCT-0001 (NOK, conflict): created.")
    elif not relationship.conflict_of_interest:
        relationship.conflict_of_interest = True
        print(f"Member relationship {SMOKE_NOK_FIXTURE_PSN} -> MCT-0001: conflict flag re-enabled.")
    else:
        print(f"Member relationship {SMOKE_NOK_FIXTURE_PSN} -> MCT-0001 (NOK, conflict): already exists.")

    seed_user(
        session, SMOKE_NOK_ADMIN_USERNAME, SMOKE_NOK_ADMIN_PASSWORD,
        UserRole.ADMIN, member=fixture, is_super_admin=True,
    )
    admin = session.execute(
        select(User).where(User.username == SMOKE_NOK_ADMIN_USERNAME)
    ).scalar_one()
    if admin.member_id != fixture.id:
        admin.member_id = fixture.id
        print(f"User {SMOKE_NOK_ADMIN_USERNAME!r}: linked to {SMOKE_NOK_FIXTURE_PSN}.")


def seed_queue_paging_fixture(session):
    """The 26 members the deduction Enter queue needs to spill onto a
    second page. They have no login and no loans -- only a contribution
    amount, which is what makes each of them due."""
    created = 0
    for index in range(1, QUEUE_FIXTURE_COUNT + 1):
        psn = f"{QUEUE_FIXTURE_PSN_PREFIX}{index:02d}"
        existing = session.execute(select(Member).where(Member.psn == psn)).scalar_one_or_none()
        if existing is not None:
            if existing.first_name != "Queue" or existing.last_name != f"Member{index:02d}":
                existing.first_name = "Queue"
                existing.last_name = f"Member{index:02d}"
                existing.other_names = "Paging"
                existing.name = compose_member_name(f"Member{index:02d}", "Queue", "Paging")
            continue
        session.add(Member(
            psn=psn,
            name=compose_member_name(f"Member{index:02d}", "Queue", "Paging"),
            first_name="Queue",
            last_name=f"Member{index:02d}",
            other_names="Paging",
            status=MemberStatus.FINANCIAL,
            email=f"{QUEUE_FIXTURE_PSN_PREFIX.lower()}{index}@example.com",
            monthly_contribution_amount=QUEUE_FIXTURE_CONTRIBUTION,
            contribution_effective_from=QUEUE_FIXTURE_EFFECTIVE_FROM,
        ))
        created += 1
    session.flush()
    print(f"Queue paging members: {created} created, "
          f"{QUEUE_FIXTURE_COUNT - created} already existed.")


def seed_arrears_fixture(session):
    """One member holding a loan that is behind schedule. No login, no
    repayments -- the missed months are the point."""
    member = session.execute(
        select(Member).where(Member.psn == ARREARS_FIXTURE_PSN)
    ).scalar_one_or_none()
    if member is None:
        member = Member(
            psn=ARREARS_FIXTURE_PSN,
            name=compose_member_name("Fixture", "Arrears", "Member"),
            first_name="Arrears",
            last_name="Fixture",
            other_names="Member",
            status=MemberStatus.FINANCIAL,
            email="qlarrears@example.com",
            monthly_contribution_amount=QUEUE_FIXTURE_CONTRIBUTION,
            contribution_effective_from=QUEUE_FIXTURE_EFFECTIVE_FROM,
        )
        session.add(member)
        session.flush()
        print(f"Arrears fixture: member {ARREARS_FIXTURE_PSN} created.")
    else:
        if member.first_name != "Arrears" or member.last_name != "Fixture":
            member.first_name, member.last_name, member.other_names = "Arrears", "Fixture", "Member"
            member.name = compose_member_name("Fixture", "Arrears", "Member")
        print(f"Arrears fixture: member {ARREARS_FIXTURE_PSN} already existed.")

    loan_type = session.execute(
        select(LoanType).where(LoanType.name == "Capital Loan")
    ).scalar_one()
    existing = session.execute(
        select(Loan).where(Loan.member_id == member.id, Loan.loan_type_id == loan_type.id)
    ).scalar_one_or_none()
    if existing:
        print("Arrears fixture: loan already exists.")
        return

    session.add(Loan(
        member_id=member.id,
        loan_type_id=loan_type.id,
        principal=ARREARS_FIXTURE_PRINCIPAL,
        interest_amount=Decimal("0.00"),
        net_disbursed=ARREARS_FIXTURE_PRINCIPAL,
        total_repayable=ARREARS_FIXTURE_PRINCIPAL,
        monthly_installment=ARREARS_FIXTURE_INSTALLMENT,
        disbursement_date=ARREARS_FIXTURE_DISBURSED,
        expected_end_date=compute_expected_end_date(
            ARREARS_FIXTURE_DISBURSED, ARREARS_FIXTURE_TENURE_MONTHS
        ),
        amount_repaid=Decimal("0.00"),
        status=LoanStatus.ACTIVE,
        notes="Sample: disbursed July, nothing repaid -- owes a catch-up line.",
    ))
    print(f"Arrears fixture: loan of {ARREARS_FIXTURE_PRINCIPAL} disbursed "
          f"{ARREARS_FIXTURE_DISBURSED} with no repayments.")


def seed_loan_types(session):
    created = 0
    for name, description, rate, tenure, flat, open_for_app in SAMPLE_LOAN_TYPES:
        existing = session.execute(select(LoanType).where(LoanType.name == name)).scalar_one_or_none()
        if existing:
            continue
        lt = LoanType(
            name=name, description=description, interest_rate=rate,
            tenure_months=tenure, flat_charge=flat, open_for_application=open_for_app,
            is_active=True,
        )
        session.add(lt)
        session.flush()
        session.add(LoanTypeRateVersion(
            loan_type_id=lt.id, interest_rate=rate, tenure_months=tenure,
            flat_charge=flat, effective_from=RATE_EFFECTIVE_FROM,
        ))
        created += 1
    print(f"Loan types: {created} created (each with one rate version effective {RATE_EFFECTIVE_FROM}), "
          f"{len(SAMPLE_LOAN_TYPES) - created} already existed.")


def seed_user(session, username, password, role, member=None,
              is_super_admin=False, must_change_password=False):
    existing = session.execute(select(User).where(User.username == username)).scalar_one_or_none()
    if existing:
        print(f"User {username!r}: already exists.")
        return
    error = validate_password_strength(password)
    if error:
        raise SystemExit(f"Seed password for {username!r} fails policy: {error}")
    session.add(User(
        username=username, password_hash=hash_password(password), role=role,
        member_id=member.id if member else None,
        must_change_password=must_change_password,
        is_active=True, account_status=AccountStatus.ACTIVE,
        is_super_admin=is_super_admin, failed_login_count=0,
    ))
    print(f"User {username!r}: created ({'super admin' if is_super_admin else role.value}"
          f"{', must change password on first login' if must_change_password else ''}).")


def main():
    print(f"Target: {DATABASE_URL}  (local sandbox)")
    seed_permissions.main()

    session = Session()
    try:
        seed_members(session)
        seed_relationship(session)
        seed_loan_types(session)
        seed_conflict_fixture(session)
        seed_queue_paging_fixture(session)
        seed_arrears_fixture(session)

        m1 = session.execute(select(Member).where(Member.psn == "MCT-0001")).scalar_one()
        m3 = session.execute(select(Member).where(Member.psn == "MCT-0003")).scalar_one()

        seed_user(session, ADMIN_USERNAME, ADMIN_PASSWORD, UserRole.ADMIN, is_super_admin=True)
        seed_user(session, "MCT-0001", MEMBER_PASSWORD, UserRole.MEMBER, member=m1)
        seed_user(session, "MCT-0003", MEMBER_PASSWORD, UserRole.MEMBER, member=m3,
                  must_change_password=True)
        session.commit()
    finally:
        session.close()

    print("\nDone. Local sandbox credentials (sample data -- never push these):")
    print(f"  Admin:        {ADMIN_USERNAME} / {ADMIN_PASSWORD}")
    print(f"  Member 1:     MCT-0001 / {MEMBER_PASSWORD}")
    print(f"  Member 2:     MCT-0003 / {MEMBER_PASSWORD}  (must_change_password=True: exercises the reset flow)")
    print(f"  Smoke NOK:    {SMOKE_NOK_ADMIN_USERNAME} / {SMOKE_NOK_ADMIN_PASSWORD}  "
          f"(admin linked to {SMOKE_NOK_FIXTURE_PSN}, whose NOK is MCT-0001; pass to "
          "smoke_test.py as --conflict-admin-user/--conflict-admin-pass)")


if __name__ == "__main__":
    main()
