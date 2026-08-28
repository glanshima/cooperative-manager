"""
Idempotency foundation (Phase 1, Section 17).

A state-changing endpoint that must not accidentally repeat its financial
effect (disbursement, repayment verification, payment verification, loan
decisions, ...) accepts an optional `Idempotency-Key` request header. This
module gives routers two small building blocks around that header rather
than a decorator, since FastAPI dependency injection composes more simply
with the existing per-route Depends(...) style used throughout the app:

    idem = Depends(idempotency_check)   # -> IdempotencyContext | None

    def my_route(..., idem: IdempotencyContext = Depends(idempotency_check)):
        if idem and idem.cached_response is not None:
            return idem.cached_response
        ... do the work ...
        result = ...
        if idem:
            idem.store(result)
        return result

If the client doesn't send an Idempotency-Key header, idempotency_check
returns a context with cached_response=None and a no-op store() -- the
endpoint behaves exactly as it did before Phase 1 introduced this. This
keeps the mechanism opt-in at the client/frontend level while the
enforcement (hash mismatch -> 409) is unconditional whenever a key *is*
supplied, so a caller can't quietly bypass it once integrated.

CONCURRENCY DESIGN (Phase 1 remediation): the original version of this
module checked "does a record exist?" and only inserted one at the very
end, in store(). Two simultaneous requests with the same key could both
observe "no record yet" and both go on to execute the underlying
financial operation -- the uniqueness constraint on IdempotencyRecord
would only be discovered by the *second* store() call, by which point
the damage (double execution) was already done.

This version closes that window by claiming the key up front: it INSERTs
a placeholder row (completed_at=NULL) and commits immediately, before
the caller does any business logic. The database's unique constraint on
(user_id, endpoint, idempotency_key) is the actual mutual-exclusion
mechanism -- only one concurrent request can win that INSERT. The loser
re-reads the row it collided with and is handled according to its state:
  - different request_hash under the same key -> 409 (client error)
  - completed_at is set                        -> replay the cached response
  - completed_at is NULL and still fresh        -> 409 "in progress, retry"
    (a genuinely concurrent duplicate; the winner is doing the work)
  - completed_at is NULL and stale (past
    PENDING_RECORD_STALE_SECONDS)               -> the previous attempt
    almost certainly crashed before finishing (Section 17 item 5, "replay
    after failed completion"); the stale row is removed and the request
    is allowed to reclaim the key and retry the operation.

This does not weaken the existing row-locking (`with_for_update()`)
protection in the disburse/verify endpoints -- that protection is
unchanged and remains the primary guard against double-processing of a
specific business row. This module's job is the separate, generic
guarantee that the Idempotency-Key mechanism itself doesn't have its own
race, since future phases are expected to reuse it on endpoints that may
not always have a natural row lock to fall back on.
"""
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Optional

from fastapi import Depends, HTTPException, Request
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from . import models
from .database import get_db
from .deps import get_current_user

# How long a pending (uncompleted) reservation is treated as "a request is
# genuinely still in flight" before being treated as abandoned/crashed and
# reclaimable by a new attempt with the same key.
PENDING_RECORD_STALE_SECONDS = 30


def _hash_body(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


@dataclass
class IdempotencyContext:
    db: Session
    user_id: Optional[str]
    endpoint: str
    key: Optional[str]
    request_hash: str
    cached_response: Optional[Any]
    _record: Optional[models.IdempotencyRecord]

    def store(self, response_body: Any, status_code: int = 200) -> None:
        if not self.key:
            return
        if self._record is None:
            # Defensive fallback only -- normal flow always has a
            # reserved record by the time store() is called.
            return
        self._record.status_code = status_code
        self._record.response_body = json.loads(json.dumps(response_body, default=str))
        self._record.completed_at = datetime.utcnow()
        self.db.add(self._record)
        self.db.commit()


def _fetch_existing(db: Session, user_id, endpoint: str, key: str):
    return (
        db.query(models.IdempotencyRecord)
        .filter(
            models.IdempotencyRecord.user_id == user_id,
            models.IdempotencyRecord.endpoint == endpoint,
            models.IdempotencyRecord.idempotency_key == key,
        )
        .with_for_update()
        .first()
    )


async def idempotency_check(
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> IdempotencyContext:
    key = request.headers.get("Idempotency-Key")
    body = await request.body()
    request_hash = _hash_body(body)
    endpoint = f"{request.method} {request.url.path}"

    if not key:
        return IdempotencyContext(
            db=db,
            user_id=str(current_user.id),
            endpoint=endpoint,
            key=None,
            request_hash=request_hash,
            cached_response=None,
            _record=None,
        )

    for _attempt in range(2):
        # --- Try to claim the key by inserting a pending reservation. ---
        reservation = models.IdempotencyRecord(
            user_id=current_user.id,
            endpoint=endpoint,
            idempotency_key=key,
            request_hash=request_hash,
        )
        db.add(reservation)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
        else:
            db.refresh(reservation)
            return IdempotencyContext(
                db=db,
                user_id=str(current_user.id),
                endpoint=endpoint,
                key=key,
                request_hash=request_hash,
                cached_response=None,
                _record=reservation,
            )

        # --- Lost the race (or a prior record already exists): inspect it. ---
        existing = _fetch_existing(db, current_user.id, endpoint, key)
        if existing is None:
            # Extremely unlikely (deleted between the failed insert and
            # this read) -- loop once more to retry the claim.
            continue

        if existing.request_hash != request_hash:
            raise HTTPException(
                status_code=409,
                detail=(
                    "This Idempotency-Key was already used with a different request "
                    "body. Use a new key for a different request."
                ),
            )

        if existing.completed_at is not None:
            return IdempotencyContext(
                db=db,
                user_id=str(current_user.id),
                endpoint=endpoint,
                key=key,
                request_hash=request_hash,
                cached_response=existing.response_body,
                _record=existing,
            )

        age = datetime.utcnow() - existing.created_at
        if age < timedelta(seconds=PENDING_RECORD_STALE_SECONDS):
            # A genuinely concurrent request is still processing this
            # same key. Do NOT proceed -- that would reintroduce the
            # double-execution race this rewrite exists to close.
            raise HTTPException(
                status_code=409,
                detail=(
                    "A request with this Idempotency-Key is already being processed. "
                    "Retry shortly."
                ),
            )

        # Stale: the request that reserved this key never completed
        # (crash, timeout, etc.) -- Section 17 item 5, "replay after
        # failed completion" must not permanently lock the key out.
        # Reclaim it and loop once to re-attempt the insert.
        db.delete(existing)
        db.commit()

    raise HTTPException(
        status_code=409,
        detail="Could not process this Idempotency-Key right now. Retry with a new key.",
    )
