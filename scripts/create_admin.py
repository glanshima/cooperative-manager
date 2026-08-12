"""
One-off script to create the first admin login. There's no self-registration
by design -- run this once to bootstrap, then use that admin account to
create member logins and any further admin accounts through the app itself
(once an admin-management UI exists; for now, re-run this script for
additional admins too).

Usage:
    export DATABASE_URL="postgresql://...same as backend/.env..."
    export SECRET_KEY="...same as backend/.env, needed because this script
                        imports backend password-hashing utilities..."
    python create_admin.py <username> <password>
"""

import os
import sys

# Make the backend package importable when running this script directly
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app.auth import hash_password  # noqa: E402

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise SystemExit("Set DATABASE_URL before running this script.")

if len(sys.argv) < 3:
    raise SystemExit("Usage: python create_admin.py <username> <password>")

username = sys.argv[1]
password = sys.argv[2]

if len(password) < 8:
    raise SystemExit("Password must be at least 8 characters.")

engine = create_engine(DATABASE_URL)
Session = sessionmaker(bind=engine)


def main():
    session = Session()

    existing = session.execute(
        text("SELECT id FROM users WHERE username = :username"), {"username": username}
    ).fetchone()
    if existing:
        raise SystemExit(f"A user with username {username!r} already exists.")

    session.execute(
        text(
            """
            INSERT INTO users
                (id, username, password_hash, role, member_id,
                 must_change_password, is_active, created_at, updated_at)
            VALUES
                (gen_random_uuid(), :username, :password_hash, 'admin', NULL,
                 false, true, now(), now())
            """
        ),
        {"username": username, "password_hash": hash_password(password)},
    )
    session.commit()
    session.close()
    print(f"Admin user {username!r} created. must_change_password is false -- "
          "change it manually in the DB if you'd like this admin to be forced "
          "to reset on first login too.")


if __name__ == "__main__":
    main()
