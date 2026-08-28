import uuid
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from .. import models, schemas, audit_service
from ..database import get_db
from ..deps import get_current_user, require_permission

router = APIRouter(prefix="/api/offices", tags=["offices"])


@router.get("", response_model=List[schemas.OfficeOut])
def list_offices(
    current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """Any authenticated user can read the office list (e.g. to show
    'Approved by: Treasurer' in the UI); only admin.office_manage can
    create/edit."""
    return db.query(models.Office).order_by(models.Office.name).all()


@router.post("", response_model=schemas.OfficeOut, status_code=201)
def create_office(
    payload: schemas.OfficeCreate,
    request: Request,
    current_user: models.User = Depends(require_permission("admin.office_manage")),
    db: Session = Depends(get_db),
):
    existing = db.query(models.Office).filter(models.Office.name == payload.name).first()
    if existing:
        raise HTTPException(status_code=409, detail="An office with this name already exists")
    office = models.Office(**payload.model_dump())
    db.add(office)
    db.commit()
    db.refresh(office)
    audit_service.log_event(
        db,
        actor=current_user,
        event_type="admin.office_created",
        action="create",
        entity_type="office",
        entity_id=str(office.id),
        new_values=payload.model_dump(),
        request=request,
    )
    return office


@router.put("/{office_id}", response_model=schemas.OfficeOut)
def update_office(
    office_id: uuid.UUID,
    payload: schemas.OfficeUpdate,
    request: Request,
    current_user: models.User = Depends(require_permission("admin.office_manage")),
    db: Session = Depends(get_db),
):
    office = db.query(models.Office).filter(models.Office.id == office_id).first()
    if not office:
        raise HTTPException(status_code=404, detail="Office not found")

    previous = {"name": office.name, "is_active": office.is_active}
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(office, field, value)
    db.commit()
    db.refresh(office)

    audit_service.log_event(
        db,
        actor=current_user,
        event_type="admin.office_updated",
        action="update",
        entity_type="office",
        entity_id=str(office.id),
        previous_values=previous,
        new_values=payload.model_dump(exclude_unset=True),
        request=request,
    )
    return office
