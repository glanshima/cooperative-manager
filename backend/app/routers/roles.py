import uuid
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from .. import models, schemas, audit_service
from ..database import get_db
from ..deps import get_current_user, require_any_permission, require_permission

router = APIRouter(tags=["roles-permissions"])


def _to_role_out(role: models.Role) -> schemas.RoleOut:
    return schemas.RoleOut(
        id=role.id,
        name=role.name,
        description=role.description,
        is_active=role.is_active,
        requires_member_link=role.requires_member_link,
        created_at=role.created_at,
        permission_codes=sorted(rp.permission.code for rp in role.permissions),
    )


@router.get("/api/permissions", response_model=List[schemas.PermissionOut])
def list_permissions(
    current_user: models.User = Depends(
        require_any_permission("admin.role_manage", "admin.permission_manage")
    ),
    db: Session = Depends(get_db),
):
    """The permission catalogue itself is code-defined and read-only over
    the API (see permissions_catalogue.py) -- what's configurable is
    which roles hold which permissions, via the roles endpoints below.

    Phase 1 remediation (Section 3): readable by admin.role_manage OR
    admin.permission_manage. A role manager needs to READ this catalogue
    to render the Roles UI's permission-matrix checkboxes even though
    they don't hold the narrower admin.permission_manage grant -- the
    catalogue itself is a fixed, code-defined list (not admin-editable
    data), so allowing a role manager to read it doesn't let them modify
    anything they couldn't already reach via the role-write endpoints
    below, which remain gated on admin.role_manage specifically."""
    return db.query(models.Permission).order_by(models.Permission.category, models.Permission.code).all()


@router.get("/api/roles", response_model=List[schemas.RoleOut])
def list_roles(
    current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """Any authenticated staff account can read the role list (needed to
    render 'assign role' pickers); only admin.role_manage can write."""
    if current_user.role != models.UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Admin access required")
    roles = db.query(models.Role).order_by(models.Role.name).all()
    return [_to_role_out(r) for r in roles]


@router.post("/api/roles", response_model=schemas.RoleOut, status_code=201)
def create_role(
    payload: schemas.RoleCreate,
    request: Request,
    current_user: models.User = Depends(require_permission("admin.role_manage")),
    db: Session = Depends(get_db),
):
    existing = db.query(models.Role).filter(models.Role.name == payload.name).first()
    if existing:
        raise HTTPException(status_code=409, detail="A role with this name already exists")

    unknown = _unknown_codes(db, payload.permission_codes)
    if unknown:
        raise HTTPException(status_code=400, detail=f"Unknown permission code(s): {', '.join(unknown)}")

    role = models.Role(
        name=payload.name,
        description=payload.description,
        is_active=payload.is_active,
        requires_member_link=payload.requires_member_link,
    )
    db.add(role)
    db.flush()
    _set_role_permissions(db, role, payload.permission_codes)
    db.commit()
    db.refresh(role)

    audit_service.log_event(
        db,
        actor=current_user,
        event_type="admin.role_created",
        action="create",
        entity_type="role",
        entity_id=str(role.id),
        new_values={"name": role.name, "permission_codes": payload.permission_codes},
        request=request,
    )
    return _to_role_out(role)


@router.put("/api/roles/{role_id}", response_model=schemas.RoleOut)
def update_role(
    role_id: uuid.UUID,
    payload: schemas.RoleUpdate,
    request: Request,
    current_user: models.User = Depends(require_permission("admin.role_manage")),
    db: Session = Depends(get_db),
):
    role = db.query(models.Role).filter(models.Role.id == role_id).first()
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")

    previous = {
        "name": role.name,
        "is_active": role.is_active,
        "requires_member_link": role.requires_member_link,
        "permission_codes": sorted(rp.permission.code for rp in role.permissions),
    }

    data = payload.model_dump(exclude_unset=True)
    permission_codes = data.pop("permission_codes", None)
    for field, value in data.items():
        setattr(role, field, value)

    if permission_codes is not None:
        unknown = _unknown_codes(db, permission_codes)
        if unknown:
            raise HTTPException(status_code=400, detail=f"Unknown permission code(s): {', '.join(unknown)}")
        _set_role_permissions(db, role, permission_codes)

    db.commit()
    db.refresh(role)

    audit_service.log_event(
        db,
        actor=current_user,
        event_type="admin.role_updated",
        action="update",
        entity_type="role",
        entity_id=str(role.id),
        previous_values=previous,
        new_values=payload.model_dump(exclude_unset=True),
        request=request,
    )
    return _to_role_out(role)


def _unknown_codes(db: Session, codes: List[str]) -> List[str]:
    if not codes:
        return []
    found = {
        p.code for p in db.query(models.Permission).filter(models.Permission.code.in_(codes)).all()
    }
    return [c for c in codes if c not in found]


def _set_role_permissions(db: Session, role: models.Role, codes: List[str]) -> None:
    db.query(models.RolePermission).filter(models.RolePermission.role_id == role.id).delete()
    permissions = db.query(models.Permission).filter(models.Permission.code.in_(codes)).all()
    for permission in permissions:
        db.add(models.RolePermission(role_id=role.id, permission_id=permission.id))
