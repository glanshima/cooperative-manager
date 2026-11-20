import base64
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from .. import audit_service, blob_storage, models, schemas, validation
from ..database import get_db
from ..deps import (
    get_current_user,
    require_admin,
    require_permission,
    user_has_permission,
)

logger = logging.getLogger("mact.settings")

router = APIRouter(prefix="/api/settings", tags=["settings"])

LOGO_EXTENSIONS = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp"}

# Owned by branding.manage rather than admin.settings_manage: editing the
# cooperative's identity is a branding decision, not routine configuration.
BRANDING_FIELDS = {"cooperative_name", "cooperative_short_name", "cooperative_monogram"}


def _get_or_create_settings(db: Session) -> models.Settings:
    """Single-row table -- create the default row on first access if it
    doesn't exist yet, rather than requiring a separate seed step."""
    settings = db.query(models.Settings).first()
    if not settings:
        settings = models.Settings()
        db.add(settings)
        db.commit()
        db.refresh(settings)
    return settings


@router.get("", response_model=schemas.SettingsOut)
def get_settings(
    current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """Any authenticated user can read settings -- members need to see
    the loan form fee before applying, for instance."""
    return _get_or_create_settings(db)


@router.put("", response_model=schemas.SettingsOut)
def update_settings(
    payload: schemas.SettingsUpdate,
    request: Request,
    current_user: models.User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Split by field: branding fields need branding.manage, everything
    else needs admin.settings_manage. Requiring both up front would force
    every branding editor to hold settings authority too, and checking
    only the payload's fields keeps a branding.manage holder from
    slipping a module toggle through the same request."""
    changes = payload.model_dump(exclude_unset=True)
    if set(changes) - BRANDING_FIELDS and not user_has_permission(
        db, current_user, "admin.settings_manage"
    ):
        raise HTTPException(
            status_code=403,
            detail="You do not have the 'admin.settings_manage' permission for this action.",
        )
    if BRANDING_FIELDS & changes.keys() and not user_has_permission(
        db, current_user, "branding.manage"
    ):
        raise HTTPException(
            status_code=403,
            detail="You do not have the 'branding.manage' permission for this action.",
        )

    settings = _get_or_create_settings(db)
    previous = {field: getattr(settings, field) for field in changes}
    for field, value in changes.items():
        setattr(settings, field, value)
    db.commit()
    db.refresh(settings)

    audit_service.log_event(
        db,
        actor=current_user,
        event_type="settings.updated",
        action="update",
        entity_type="settings",
        entity_id=str(settings.id) if hasattr(settings, "id") else "settings",
        previous_values=previous,
        new_values=changes,
        request=request,
    )
    return settings


@router.post("/logo", response_model=schemas.SettingsOut)
def upload_logo(
    payload: schemas.LogoUploadIn,
    request: Request,
    current_user: models.User = Depends(require_permission("branding.manage")),
    db: Session = Depends(get_db),
):
    """Replace the cooperative logo. The declared content type is checked
    against the actual bytes, because the stored URL is served publicly and
    the extension in it follows the sniffed type, not the request."""
    settings = _get_or_create_settings(db)
    data = base64.b64decode(payload.image_base64, validate=True)

    detected = validation.detect_image_content_type(data)
    if detected is None or detected != payload.content_type:
        raise HTTPException(
            status_code=400,
            detail="Logo must be a PNG, JPEG or WebP image whose content matches its declared type.",
        )
    if len(data) > validation.MAX_LOGO_BYTES:
        raise HTTPException(status_code=400, detail="Logo file is too large (maximum 1 MB).")

    pathname = f"branding/cooperative-logo-{uuid.uuid4().hex[:12]}.{LOGO_EXTENSIONS[detected]}"
    try:
        blob = blob_storage.upload_blob(pathname=pathname, data=data, content_type=detected)
    except blob_storage.BlobNotConfigured:
        raise HTTPException(
            status_code=503,
            detail="Logo storage is not configured for this deployment. Set BLOB_READ_WRITE_TOKEN on the API.",
        )
    except blob_storage.BlobOperationFailed as exc:
        logger.error("Logo upload failed: %s", exc)
        raise HTTPException(status_code=502, detail="Could not store the logo. Please try again.")

    previous_url = settings.logo_url
    settings.logo_url = blob["url"]
    db.commit()
    db.refresh(settings)

    audit_service.log_event(
        db,
        actor=current_user,
        event_type="settings.logo_uploaded",
        action="upload",
        entity_type="settings",
        entity_id=str(settings.id),
        previous_values={"logo_url": previous_url},
        new_values={"logo_url": settings.logo_url},
        request=request,
    )

    # The replacement is already live; a failed cleanup only leaks an orphan
    # blob, which must not turn a successful upload into an error.
    if previous_url:
        try:
            blob_storage.delete_blob(previous_url)
        except blob_storage.BlobOperationFailed as exc:
            logger.warning("Could not delete replaced logo blob %s: %s", previous_url, exc)

    return settings


@router.delete("/logo", response_model=schemas.SettingsOut)
def remove_logo(
    request: Request,
    current_user: models.User = Depends(require_permission("branding.manage")),
    db: Session = Depends(get_db),
):
    settings = _get_or_create_settings(db)
    if not settings.logo_url:
        return settings

    # Unlike a replacement, deleting the only copy is the whole point of the
    # request, so a storage failure keeps the record pointing at a logo that
    # still exists instead of silently reporting success.
    try:
        blob_storage.delete_blob(settings.logo_url)
    except blob_storage.BlobNotConfigured:
        raise HTTPException(
            status_code=503,
            detail="Logo storage is not configured for this deployment. Set BLOB_READ_WRITE_TOKEN on the API.",
        )
    except blob_storage.BlobOperationFailed as exc:
        logger.error("Logo delete failed: %s", exc)
        raise HTTPException(status_code=502, detail="Could not remove the logo. Please try again.")

    previous_url = settings.logo_url
    settings.logo_url = None
    db.commit()
    db.refresh(settings)

    audit_service.log_event(
        db,
        actor=current_user,
        event_type="settings.logo_removed",
        action="delete",
        entity_type="settings",
        entity_id=str(settings.id),
        previous_values={"logo_url": previous_url},
        new_values={"logo_url": None},
        request=request,
    )
    return settings
