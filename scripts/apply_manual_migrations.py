"""
Applies the project's manual SQL migrations (scripts/manual_migration_*.sql)
in a single, explicitly-ordered pass against a target database.

Background: this project has no alembic-driven migration history in use --
the app's Base.metadata.create_all() creates missing TABLES on boot but
never adds missing COLUMNS to tables that already exist, so schema changes
to existing tables ship as hand-run SQL files in scripts/. Those files were
written to be idempotent (IF NOT EXISTS guards, defensive DO blocks), and
this runner exists so they are applied in the right order, in one command,
with one report -- instead of someone opening Neon's SQL editor and
copying files in by hand.

Where it's safe to point it:
  - The local offline sandbox (127.0.0.1:55432) -- the default use case.
  - A Neon BRANCH (or any non-production database) -- pass --allow-remote
    explicitly; the flag is a deliberate speed bump, not a formality.
This script never writes sample data; it only applies schema SQL.

Idempotency: every file can be re-run. Files whose objects already exist
raise Postgres "duplicate object" errors, which are treated as
"already applied" (see DUPLICATE_CODES); any other error stops the run.

Usage:
    # local sandbox (DATABASE_URL defaults to backend/.env, which points there)
    backend/.venv/Scripts/python.exe scripts/apply_manual_migrations.py

    # a Neon branch, before deploying backend code that needs the schema
    DATABASE_URL="postgresql://...ep-xxx-branch.../db?sslmode=require" \
        backend/.venv/Scripts/python.exe scripts/apply_manual_migrations.py --allow-remote
"""
import argparse
import os
import sys
from urllib.parse import urlparse

import dotenv

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(ROOT, "backend"))

dotenv.load_dotenv(os.path.join(ROOT, "backend", ".env"), override=False)

SANDBOX_HOSTS = {"127.0.0.1", "localhost"}
SANDBOX_PORT = 55432

# Explicit, dependency-checked order -- do not "fix" this into filename
# sort order. Alphabetical sorting puts phase1_db_integrity_constraints
# BEFORE phase1_security_foundation, and the constraints file references
# tables (roles, permissions, users columns) that the foundation file
# creates. Rationale for the rest: the foundation creates the governance
# tables everything later touches; column-adding files come before the
# constraints file that validates those columns; the two 2026-09 files
# are chronologically last.
ORDERED_MIGRATIONS = [
    "manual_migration_2026_08_phase1_security_foundation.sql",
    "manual_migration_2026_08_add_loan_application_columns.sql",
    "manual_migration_2026_08_loan_features_batch2.sql",
    "manual_migration_2026_08_round1_description.sql",
    "manual_migration_2026_08_round2.sql",
    "manual_migration_2026_08_admin_governance_member_link_enforcement.sql",
    "manual_migration_2026_08_admin_identity_governance.sql",
    "manual_migration_2026_08_controlled_remediation_user_member_link.sql",
    "manual_migration_2026_08_phase1_db_integrity_constraints.sql",
    "manual_migration_2026_09_member_relationships.sql",
    "manual_migration_2026_09_secure_password_recovery.sql",
    "manual_migration_2026_11_payroll_deductions.sql",
    "manual_migration_2026_11_unique_active_loan_type.sql",
    "manual_migration_2026_11_membership_exit.sql",
    "manual_migration_2026_11_contribution_amounts.sql",
    "manual_migration_2026_11_loan_arrears_lines.sql",
]

# Postgres SQLSTATEs meaning "this object already exists" -- treated as
# "file already applied" because every migration here is additive.
DUPLICATE_CODES = {
    "42710",  # duplicate_object (constraints, etc.)
    "42723",  # duplicate_function
    "42P06",  # duplicate_schema
    "42P07",  # duplicate_table
    "42701",  # duplicate_column
}

# create_all() builds tables from the CURRENT models, and SQLAlchemy's
# Python-side defaults (default=False, default=0, ...) do NOT become
# database server defaults. The same columns were added to real databases
# by migrations WITH server defaults, and raw-SQL scripts written for the
# real database rely on those (seed_permissions.py INSERTs into roles
# without requires_member_link). These idempotent ALTERs restore parity so
# the sandbox behaves like a migrated database. On prod, SET DEFAULT to
# the value the migration already set is a no-op.
SERVER_DEFAULT_FIXUPS = [
    ("roles", "requires_member_link", "false"),
    ("members", "loan_restricted", "false"),
    ("loan_types", "open_for_application", "false"),
    ("loan_types", "flat_charge", "0"),
    ("loan_applications", "use_default_account", "true"),
    ("users", "account_status", "'active'"),
    ("users", "is_super_admin", "false"),
    ("users", "failed_login_count", "0"),
]


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument(
        "--allow-remote",
        action="store_true",
        help="Required to run against a non-sandbox database (e.g. a Neon branch).",
    )
    args = parser.parse_args()

    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise SystemExit(
            "DATABASE_URL is not set. Either export it or rely on backend/.env "
            "(this script loads backend/.env without overriding real env vars)."
        )

    parsed = urlparse(database_url)
    is_sandbox = parsed.hostname in SANDBOX_HOSTS and parsed.port == SANDBOX_PORT
    if not is_sandbox and not args.allow_remote:
        raise SystemExit(
            f"REFUSING TO RUN against {parsed.hostname}:{parsed.port} -- not the local "
            f"sandbox ({sorted(SANDBOX_HOSTS)}:{SANDBOX_PORT}). If this is a Neon branch "
            "or another disposable database, re-run with --allow-remote."
        )
    target_label = "local sandbox" if is_sandbox else f"REMOTE ({parsed.hostname})"
    print(f"Target: {database_url}  [{target_label}]\n")

    # Same code path the app uses on boot: create any missing tables as
    # they exist in the CURRENT models. The migration files below then
    # bring an older database's existing tables up to date.
    from app.models import Base  # noqa: E402
    from sqlalchemy import create_engine  # noqa: E402

    engine = create_engine(database_url)
    Base.metadata.create_all(bind=engine)
    print("create_all(): base schema ensured (missing tables created).\n")

    import psycopg2  # noqa: E402

    applied, skipped = [], []
    conn = psycopg2.connect(database_url)
    try:
        for filename in ORDERED_MIGRATIONS:
            path = os.path.join(SCRIPTS_DIR, filename)
            with open(path, encoding="utf-8") as fh:
                sql = fh.read()
            try:
                with conn.cursor() as cur:
                    cur.execute(sql)
                conn.commit()
                applied.append(filename)
                print(f"  applied : {filename}")
            except psycopg2.Error as err:
                conn.rollback()
                if err.pgcode in DUPLICATE_CODES:
                    skipped.append(filename)
                    print(f"  already : {filename}  (objects already exist)")
                else:
                    print(f"\nFAILED on {filename} (SQLSTATE {err.pgcode}):\n{err}")
                    raise SystemExit(1)

        print("\nServer-default parity (create_all vs migrated schema):")
        for table, column, default in SERVER_DEFAULT_FIXUPS:
            with conn.cursor() as cur:
                cur.execute(
                    f'ALTER TABLE {table} ALTER COLUMN "{column}" SET DEFAULT {default}'
                )
            conn.commit()
            print(f"  {table}.{column} -> DEFAULT {default}")
    finally:
        conn.close()

    print(f"\nDone. {len(applied)} file(s) applied, {len(skipped)} already applied.")
    if skipped and not is_sandbox:
        print(
            "Note: 'already applied' means every statement in those files was a "
            "duplicate of what already exists -- expected on a branch of a "
            "database that has received these migrations before."
        )


if __name__ == "__main__":
    main()
