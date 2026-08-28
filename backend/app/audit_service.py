"""
Audit-event write helper (Phase 1, Sections 13-14).

Usage pattern in a router, after a state change has been committed:

    audit_service.log_event(
        db,
        actor=current_user,
        request=request,
        event_type="loan_application.decided",
        entity_type="loan_application",
        entity_id=str(application.id),
        action="approve",
        previous_values={"status": "pending"},
        new_values={"status": "approved", "approved_amount": str(payload.approved_amount)},
        reason=payload.admin_notes,
    )

Design notes:
- Audit writes are committed in their own small transaction, separate
  from the business-transaction commit that already happened, so a
  failure writing the audit event never rolls back (or blocks) the
  underlying financial action.
- WHY NOT FULLY ATOMIC (Phase 1 remediation, Section 5): making the audit
  write part of the *same* database transaction as the business change
  would be the strongest guarantee, but several already-committed Phase 1
  routers call `db.commit()` for the business change first and only then
  build the audit payload (e.g. so they can include the newly-generated
  id / server-computed values in new_values). Restructuring every one of
  those call sites to defer the business commit until after the audit
  event is also staged is a real, cross-cutting change to transaction
  boundaries across ~8 routers -- exactly the kind of "casually redesign
  the whole accounting architecture" this prompt says not to do mid-Phase-1.
  The practical Phase 1 fix below is therefore: (1) never let an audit
  failure be silent, and (2) make failures loud/operationally visible via
  the standard logging pipeline instead of a bare print() that most
  hosting setups (e.g. Vercel serverless functions) don't reliably
  aggregate or alert on. Making the business+audit write fully atomic is
  recorded as a follow-up for Phase 3 (Accounting Foundation), when
  transaction boundaries are being revisited anyway.
- On failure, this module raises AuditWriteFailed after logging, so a
  caller that wants a state-changing endpoint to hard-fail when its audit
  event can't be written (rather than silently continuing) can choose to
  let that exception propagate. Existing Phase 1 call sites do not catch
  it, so today a failed audit write surfaces as a 500 to the client
  rather than a silent success -- an intentional, conservative choice:
  for financial state changes, "the action succeeded but we couldn't
  prove it happened" is worse than a loud error asking the operator to
  check the logs and, if needed, retry.
- previous_values/new_values are plain dicts the caller builds -- pass
  only the fields that changed, not a full-row dump, and always run
  free-text/secret-bearing fields through redact() first.
- actor can be None for unauthenticated events (e.g. a failed login for
  a username that doesn't exist) -- pass actor_username explicitly in
  that case via the actor_username_override parameter.
"""
import json
import logging
from datetime import datetime
from typing import Optional

from fastapi import Request
from sqlalchemy.orm import Session

from . import models

logger = logging.getLogger("mact.audit")


class AuditWriteFailed(RuntimeError):
    """Raised (after logging) when an audit event could not be persisted.
    Deliberately a plain RuntimeError subclass, not an HTTPException --
    audit_service has no business knowing what HTTP status a given
    router should return; callers that want a specific status can catch
    this and translate it themselves."""

REDACTED_KEYS = {
    "password",
    "password_hash",
    "current_password",
    "new_password",
    "temporary_password",
    "token",
    "access_token",
    "secret_key",
}


def redact(values: Optional[dict]) -> Optional[dict]:
    if values is None:
        return None
    return {k: ("***redacted***" if k.lower() in REDACTED_KEYS else v) for k, v in values.items()}


def _json_safe(values: Optional[dict]) -> Optional[dict]:
    """Coerce non-JSON-native types (UUID, Decimal, date/datetime, enums)
    to strings so the JSONB column always accepts the payload."""
    if values is None:
        return None
    return json.loads(json.dumps(values, default=str))


def _client_meta(request: Optional[Request]):
    if request is None:
        return None, None, None
    ip = request.client.host if request.client else None
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        ip = forwarded.split(",")[0].strip()
    user_agent = request.headers.get("user-agent")
    request_reference = request.headers.get("x-request-id")
    return ip, user_agent, request_reference


def _actor_snapshot(db: Session, actor: Optional[models.User]):
    if actor is None:
        return None, None, None
    office_names = []
    role_names = []
    for assignment in actor.role_assignments:
        if not assignment.is_active:
            continue
        if assignment.office is not None:
            office_names.append(assignment.office.name)
        if assignment.role is not None:
            role_names.append(assignment.role.name)
    return (
        ", ".join(sorted(set(office_names))) or None,
        ", ".join(sorted(set(role_names))) or None,
    )


def log_event(
    db: Session,
    *,
    actor: Optional[models.User],
    event_type: str,
    action: str,
    entity_type: Optional[str] = None,
    entity_id: Optional[str] = None,
    previous_values: Optional[dict] = None,
    new_values: Optional[dict] = None,
    reason: Optional[str] = None,
    request: Optional[Request] = None,
    actor_username_override: Optional[str] = None,
) -> models.AuditEvent:
    ip, user_agent, request_reference = _client_meta(request)
    office_name, role_names = _actor_snapshot(db, actor)

    event = models.AuditEvent(
        actor_user_id=actor.id if actor else None,
        actor_username=(actor.username if actor else actor_username_override),
        actor_office_name=office_name,
        actor_role_names=role_names,
        event_type=event_type,
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        previous_values=_json_safe(redact(previous_values)),
        new_values=_json_safe(redact(new_values)),
        reason=reason,
        ip_address=ip,
        user_agent=user_agent,
        request_reference=request_reference,
        timestamp=datetime.utcnow(),
    )
    try:
        db.add(event)
        db.commit()
    except Exception as exc:
        db.rollback()
        # logger.critical (not .error) plus exc_info: this must be
        # impossible to miss in whatever log aggregation the deployment
        # target uses -- a lost audit event for a state-changing action
        # is a compliance-relevant failure, not a routine warning.
        logger.critical(
            "AUDIT WRITE FAILED event_type=%r entity_type=%r entity_id=%r "
            "actor_user_id=%r action=%r: %s",
            event_type,
            entity_type,
            entity_id,
            actor.id if actor else None,
            action,
            exc,
            exc_info=True,
        )
        raise AuditWriteFailed(
            f"Failed to write audit event {event_type!r} for {entity_type}:{entity_id}"
        ) from exc
    return event
