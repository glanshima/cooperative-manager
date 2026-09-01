"""
Member-to-Member Relationship / Next-of-Kin Controlled Remediation
(2026-09).

Central, reusable place for creating, changing, and removing
MemberRelationship rows, plus a conflict-lookup helper
(has_member_conflict) that is FOUNDATIONAL ONLY -- it deliberately is
not called from any loan/disbursement/repayment approval path in this
pass. Section 13 of the remediation prompt is explicit that wiring
member-to-member conflicts into approval workflows is future work, not
part of this remediation; that mirrors self_conflict.py's existing
User<->Member self-dealing check, which this is a natural sibling to
without duplicating or replacing it. Routers call the functions here
rather than touching MemberRelationship rows directly, the same way
they call self_conflict.require_no_self_conflict() and
account_lifecycle.set_account_status() instead of hand-rolling that
logic inline.

DESIGN NOTES
------------
- Only one relationship_type exists today (NEXT_OF_KIN), but every
  function here takes relationship_type explicitly rather than
  hard-coding it, so a future relationship type (e.g. guarantor) can
  reuse this module without a rewrite.
- "Change to a different related member" is remove-old + create-new,
  never an in-place update of related_member_id, so audit history
  (Section 17) shows exactly who the previous Next of Kin was and when
  the change happened, not just the current value.
- Nothing here deletes a row. clear_relationship() sets
  status=REMOVED + removed_at/removed_by_user_id.
"""
import uuid
from typing import Optional

from fastapi import HTTPException, Request
from sqlalchemy import and_, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from . import audit_service, models


def get_active_relationship(
    db: Session,
    member_id: uuid.UUID,
    relationship_type: models.RelationshipType = models.RelationshipType.NEXT_OF_KIN,
) -> Optional[models.MemberRelationship]:
    """The single active relationship of this type FOR member_id (i.e.
    member_id is the "owning" side), if any. See MemberRelationship's
    docstring for why this is at-most-one per (member_id, type)."""
    return (
        db.query(models.MemberRelationship)
        .filter(
            models.MemberRelationship.member_id == member_id,
            models.MemberRelationship.relationship_type == relationship_type,
            models.MemberRelationship.status == models.RelationshipStatus.ACTIVE,
        )
        .first()
    )


def set_relationship(
    db: Session,
    *,
    member: models.Member,
    related_member_id: uuid.UUID,
    actor: models.User,
    relationship_type: models.RelationshipType = models.RelationshipType.NEXT_OF_KIN,
    request: Optional[Request] = None,
) -> models.MemberRelationship:
    """
    Set (create, or replace if changing to a different related member)
    the active relationship of `relationship_type` FOR `member`.
    Raises HTTPException on invalid input -- callers in routers/
    members.py don't need to re-check these themselves.

    - 404 if related_member_id doesn't resolve to a real Member.
    - 409 (self-reference) if related_member_id == member.id -- a
      member can never be their own Next of Kin. This is the primary
      enforcement point; the DB CHECK constraint on MemberRelationship
      is defense in depth, not the first line of defense, so this
      raises a clean, specific error rather than surfacing a raw
      IntegrityError to the caller.
    - No-ops (returns the existing row unchanged) if the current active
      relationship already points at the same related_member_id --
      avoids a pointless remove+recreate (and a pointless audit
      "changed" event) when nothing actually changed.
    """
    if related_member_id == member.id:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "self_reference",
                "message": "A member cannot be their own Next of Kin.",
            },
        )

    related_member = db.query(models.Member).filter(models.Member.id == related_member_id).first()
    if not related_member:
        raise HTTPException(status_code=404, detail="Next-of-Kin member not found")

    existing = get_active_relationship(db, member.id, relationship_type)
    if existing is not None and existing.related_member_id == related_member_id:
        return existing

    previous_related_id = None
    if existing is not None:
        previous_related_id = str(existing.related_member_id)
        _remove_relationship_row(db, existing, actor)
        # Flush the UPDATE (existing row -> status='removed') before
        # adding the new row below. Without this, SQLAlchemy's unit of
        # work is free to order the new row's INSERT before the old
        # row's UPDATE within the same flush -- which would momentarily
        # have TWO active rows for (member_id, relationship_type) and
        # spuriously trip the partial unique index
        # (ux_member_relationships_one_active_per_type) even though the
        # net change is a clean swap. Flushing here forces the UPDATE to
        # land first; both statements still commit together below, so a
        # later failure still rolls back the whole swap atomically.
        db.flush()

    new_relationship = models.MemberRelationship(
        member_id=member.id,
        related_member_id=related_member_id,
        relationship_type=relationship_type,
        created_by_user_id=actor.id,
    )
    db.add(new_relationship)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        # Backstop for the partial unique index (ux_member_relationships_
        # one_active_per_type) / CHECK constraint, in case of a race
        # between the read above and this write -- mirrors
        # admin_users.py's update_admin_user_member_link IntegrityError
        # handling for the same class of race.
        raise HTTPException(
            status_code=409,
            detail="This member already has an active relationship of this type.",
        )
    db.refresh(new_relationship)

    audit_service.log_event(
        db,
        actor=actor,
        event_type="member_relationship.set",
        action="update" if previous_related_id else "create",
        entity_type="member_relationship",
        entity_id=str(new_relationship.id),
        previous_values={"related_member_id": previous_related_id} if previous_related_id else None,
        new_values={
            "member_id": str(member.id),
            "related_member_id": str(related_member_id),
            "relationship_type": relationship_type.value,
        },
        request=request,
    )
    return new_relationship


def clear_relationship(
    db: Session,
    *,
    member: models.Member,
    actor: models.User,
    relationship_type: models.RelationshipType = models.RelationshipType.NEXT_OF_KIN,
    request: Optional[Request] = None,
) -> None:
    """Remove (never hard-delete) the active relationship of this type
    FOR `member`, if one exists. A no-op if none exists."""
    existing = get_active_relationship(db, member.id, relationship_type)
    if existing is None:
        return
    removed_related_id = str(existing.related_member_id)
    relationship_id = str(existing.id)
    _remove_relationship_row(db, existing, actor)
    db.commit()

    audit_service.log_event(
        db,
        actor=actor,
        event_type="member_relationship.removed",
        action="remove",
        entity_type="member_relationship",
        entity_id=relationship_id,
        previous_values={"related_member_id": removed_related_id},
        new_values=None,
        request=request,
    )


def _remove_relationship_row(db: Session, relationship: models.MemberRelationship, actor: models.User) -> None:
    """Marks a row REMOVED in-session without committing -- callers
    commit once, after also staging whatever replaces it (if anything),
    so a set_relationship() replace is a single atomic commit rather
    than two."""
    from datetime import datetime as _datetime

    relationship.status = models.RelationshipStatus.REMOVED
    relationship.removed_at = _datetime.utcnow()
    relationship.removed_by_user_id = actor.id


def has_member_conflict(
    db: Session,
    member_a_id: Optional[uuid.UUID],
    member_b_id: Optional[uuid.UUID],
) -> bool:
    """
    Governance foundation only (Section 12 of the remediation prompt):
    answers "does an active, conflict-flagged MemberRelationship exist
    between these two members, in either direction?" -- nothing more.

    NOT WIRED INTO ANY APPROVAL PATH IN THIS PASS. This is intentional
    (Section 13-14): loan/disbursement/repayment approval continues to
    use only self_conflict.py's User.member_id-based check, exactly as
    before. This function exists so a later phase can wire
    member-to-member conflicts (e.g. "the Loan Officer approving this
    application is the applicant's registered Next of Kin") into
    approval authorization without another schema/migration pass --
    see MemberRelationship's conflict_of_interest column docstring.

    Checks BOTH directions from the single stored row (see
    MemberRelationship's docstring on why there's no mirrored reverse
    row) and returns False for a None id or when the two ids are equal
    (not a meaningful pairing).
    """
    if member_a_id is None or member_b_id is None or member_a_id == member_b_id:
        return False
    return (
        db.query(models.MemberRelationship)
        .filter(
            models.MemberRelationship.status == models.RelationshipStatus.ACTIVE,
            models.MemberRelationship.conflict_of_interest.is_(True),
            or_(
                and_(
                    models.MemberRelationship.member_id == member_a_id,
                    models.MemberRelationship.related_member_id == member_b_id,
                ),
                and_(
                    models.MemberRelationship.member_id == member_b_id,
                    models.MemberRelationship.related_member_id == member_a_id,
                ),
            ),
        )
        .first()
        is not None
    )
