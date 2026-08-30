"""
Seeds the permissions/roles/role_permissions tables from the authoritative
catalogue in backend/app/permissions_catalogue.py. Safe to re-run: it
upserts permissions by code and only creates a default role if one with
that name doesn't already exist (it will NOT overwrite an admin's
customization of an existing role's permission grants on re-run).

Usage:
    export DATABASE_URL="postgresql://...same as backend/.env..."
    python seed_permissions.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app.permissions_catalogue import PERMISSION_CATALOGUE, DEFAULT_ROLES  # noqa: E402

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise SystemExit("Set DATABASE_URL before running this script.")

engine = create_engine(DATABASE_URL)
Session = sessionmaker(bind=engine)


def main():
    session = Session()

    for code, category, description in PERMISSION_CATALOGUE:
        existing = session.execute(
            text("SELECT id FROM permissions WHERE code = :code"), {"code": code}
        ).fetchone()
        if existing:
            session.execute(
                text(
                    "UPDATE permissions SET category = :category, description = :description WHERE code = :code"
                ),
                {"code": code, "category": category, "description": description},
            )
        else:
            session.execute(
                text(
                    """
                    INSERT INTO permissions (id, code, category, description, created_at)
                    VALUES (gen_random_uuid(), :code, :category, :description, now())
                    """
                ),
                {"code": code, "category": category, "description": description},
            )
    session.commit()
    print(f"Seeded/updated {len(PERMISSION_CATALOGUE)} permissions.")

    for role_name, spec in DEFAULT_ROLES.items():
        existing_role = session.execute(
            text("SELECT id FROM roles WHERE name = :name"), {"name": role_name}
        ).fetchone()
        if existing_role:
            print(f"Role {role_name!r} already exists -- leaving its permission grants untouched.")
            continue

        role_id = session.execute(
            text(
                """
                INSERT INTO roles (id, name, description, is_active, created_at, updated_at)
                VALUES (gen_random_uuid(), :name, :description, true, now(), now())
                RETURNING id
                """
            ),
            {"name": role_name, "description": spec["description"]},
        ).scalar()

        for code in spec["permissions"]:
            permission_id = session.execute(
                text("SELECT id FROM permissions WHERE code = :code"), {"code": code}
            ).scalar()
            if not permission_id:
                print(f"  WARNING: permission code {code!r} not found, skipping")
                continue
            session.execute(
                text(
                    """
                    INSERT INTO role_permissions (id, role_id, permission_id)
                    VALUES (gen_random_uuid(), :role_id, :permission_id)
                    """
                ),
                {"role_id": role_id, "permission_id": permission_id},
            )
        session.commit()
        print(f"Created default role {role_name!r} with {len(spec['permissions'])} permissions.")

    session.close()
    print("Done. Assign roles to admin users via POST /api/admin/users/{user_id}/assignments.")


if __name__ == "__main__":
    main()
