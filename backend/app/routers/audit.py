import uuid
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from .. import models, schemas, audit_service
from ..database import get_db
from ..deps import require_permission

router = APIRouter(prefix="/api/audit", tags=["audit"])


@router.get("", response_model=List[schemas.AuditEventOut])
def list_audit_events(
    entity_type: Optional[str] = None,
    entity_id: Optional[str] = None,
    event_type: Optional[str] = None,
    actor_user_id: Optional[uuid.UUID] = None,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    skip: int = 0,
    limit: int = Query(default=100, le=500),
    current_user: models.User = Depends(require_permission("audit.view")),
    db: Session = Depends(get_db),
):
    """Ordinary members never reach this endpoint -- require_permission
    already rejects non-admin accounts, and admin accounts additionally
    need the audit.view permission explicitly granted."""
    query = db.query(models.AuditEvent)
    if entity_type:
        query = query.filter(models.AuditEvent.entity_type == entity_type)
    if entity_id:
        query = query.filter(models.AuditEvent.entity_id == entity_id)
    if event_type:
        query = query.filter(models.AuditEvent.event_type == event_type)
    if actor_user_id:
        query = query.filter(models.AuditEvent.actor_user_id == actor_user_id)
    if start_time:
        query = query.filter(models.AuditEvent.timestamp >= start_time)
    if end_time:
        query = query.filter(models.AuditEvent.timestamp <= end_time)

    return (
        query.order_by(models.AuditEvent.timestamp.desc()).offset(skip).limit(limit).all()
    )


@router.get("/{event_id}", response_model=schemas.AuditEventOut)
def get_audit_event(
    event_id: uuid.UUID,
    current_user: models.User = Depends(require_permission("audit.view")),
    db: Session = Depends(get_db),
):
    event = db.query(models.AuditEvent).filter(models.AuditEvent.id == event_id).first()
    if not event:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Audit event not found")
    return event


@router.get("/export/csv")
def export_audit_events_csv(
    entity_type: Optional[str] = None,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    current_user: models.User = Depends(require_permission("audit.export")),
    db: Session = Depends(get_db),
):
    import csv
    import io

    from fastapi.responses import StreamingResponse

    query = db.query(models.AuditEvent)
    if entity_type:
        query = query.filter(models.AuditEvent.entity_type == entity_type)
    if start_time:
        query = query.filter(models.AuditEvent.timestamp >= start_time)
    if end_time:
        query = query.filter(models.AuditEvent.timestamp <= end_time)
    events = query.order_by(models.AuditEvent.timestamp.desc()).limit(5000).all()

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        ["timestamp", "actor_username", "event_type", "entity_type", "entity_id", "action", "reason"]
    )
    for e in events:
        writer.writerow(
            [e.timestamp.isoformat(), e.actor_username, e.event_type, e.entity_type, e.entity_id, e.action, e.reason]
        )
    buffer.seek(0)

    audit_service.log_event(
        db,
        actor=current_user,
        event_type="audit.exported",
        action="export",
        reason=f"{len(events)} events exported",
    )

    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=audit_export.csv"},
    )
