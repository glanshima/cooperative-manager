import base64

from tests.conftest import auth_headers, grant_permission, make_admin_user, make_member, make_member_user

PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
JPEG_BYTES = b"\xff\xd8\xff\xe0" + b"\x00" * 64


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode()


def _admin_with_settings_permission(db_session, username="brand_admin"):
    admin = make_admin_user(db_session, username=username)
    grant_permission(db_session, admin, "admin.settings_manage")
    return admin


def test_public_branding_returns_defaults_without_auth_and_without_creating_settings(client, db_session):
    from app import models

    res = client.get("/api/branding")

    assert res.status_code == 200
    assert res.json() == {
        "cooperative_name": "MACT Cooperative",
        "cooperative_short_name": "MACT",
        "cooperative_monogram": "M",
        "logo_url": None,
    }
    # A signed-out read must not have the side effect of creating a row.
    assert db_session.query(models.Settings).count() == 0


def test_public_branding_exposes_only_the_branding_slice(client, db_session):
    from app import models

    db_session.add(models.Settings(cooperative_name="Unity Cooperative", cooperative_short_name="Unity"))
    db_session.commit()

    payload = client.get("/api/branding").json()

    assert payload["cooperative_name"] == "Unity Cooperative"
    assert payload["cooperative_short_name"] == "Unity"
    assert set(payload) == {"cooperative_name", "cooperative_short_name", "cooperative_monogram", "logo_url"}


def test_update_branding_fields_through_settings_put(client, db_session, seed_permissions):
    from app import models

    admin = _admin_with_settings_permission(db_session, "brand_put_admin")

    res = client.put(
        "/api/settings",
        json={
            "cooperative_name": "  MACT  Cooperative  Society ",
            "cooperative_short_name": "MACT",
            "cooperative_monogram": "MC",
        },
        headers=auth_headers(admin),
    )

    assert res.status_code == 200
    body = res.json()
    # Whitespace is collapsed so the stored name and the rendered name agree.
    assert body["cooperative_name"] == "MACT Cooperative Society"
    assert body["cooperative_monogram"] == "MC"

    event = (
        db_session.query(models.AuditEvent)
        .filter(models.AuditEvent.event_type == "settings.updated")
        .first()
    )
    assert event is not None
    assert event.new_values["cooperative_name"] == "MACT Cooperative Society"
    assert event.previous_values["cooperative_name"] == "MACT Cooperative"


def test_branding_name_cannot_be_blank(client, db_session, seed_permissions):
    admin = _admin_with_settings_permission(db_session, "brand_blank_admin")

    res = client.put(
        "/api/settings",
        json={"cooperative_name": "   "},
        headers=auth_headers(admin),
    )

    assert res.status_code == 422


def test_branding_name_cannot_exceed_the_column_width(client, db_session, seed_permissions):
    admin = _admin_with_settings_permission(db_session, "brand_long_admin")

    res = client.put(
        "/api/settings",
        json={"cooperative_name": "C" * 121},
        headers=auth_headers(admin),
    )

    assert res.status_code == 422


def test_branding_update_requires_settings_permission(client, db_session, seed_permissions):
    admin = make_admin_user(db_session, username="brand_noperm_admin")

    res = client.put(
        "/api/settings",
        json={"cooperative_name": "Renamed Cooperative"},
        headers=auth_headers(admin),
    )

    assert res.status_code == 403


def _stub_blob(monkeypatch, url="https://blob.example.test/logo.png", uploads=None, deletes=None):
    from app import blob_storage

    def fake_upload(pathname, data, content_type):
        if uploads is not None:
            uploads.append({"pathname": pathname, "content_type": content_type, "size": len(data)})
        return {"url": url, "pathname": pathname}

    def fake_delete(blob_url):
        if deletes is not None:
            deletes.append(blob_url)

    monkeypatch.setattr(blob_storage, "upload_blob", fake_upload)
    monkeypatch.setattr(blob_storage, "delete_blob", fake_delete)


def test_logo_upload_stores_blob_and_audits(client, db_session, seed_permissions, monkeypatch):
    from app import models

    admin = _admin_with_settings_permission(db_session, "brand_logo_admin")
    uploads = []
    _stub_blob(monkeypatch, url="https://blob.example.test/branding/logo.png", uploads=uploads)

    res = client.post(
        "/api/settings/logo",
        json={"content_type": "image/png", "image_base64": _b64(PNG_BYTES)},
        headers=auth_headers(admin),
    )

    assert res.status_code == 200
    assert res.json()["logo_url"] == "https://blob.example.test/branding/logo.png"
    assert uploads[0]["content_type"] == "image/png"
    assert uploads[0]["pathname"].startswith("branding/cooperative-logo-")
    assert uploads[0]["pathname"].endswith(".png")

    event = (
        db_session.query(models.AuditEvent)
        .filter(models.AuditEvent.event_type == "settings.logo_uploaded")
        .first()
    )
    assert event is not None
    assert event.new_values["logo_url"] == "https://blob.example.test/branding/logo.png"


def test_logo_upload_rejects_a_declared_type_that_does_not_match_the_bytes(
    client, db_session, seed_permissions, monkeypatch
):
    admin = _admin_with_settings_permission(db_session, "brand_mismatch_admin")
    _stub_blob(monkeypatch)

    res = client.post(
        "/api/settings/logo",
        json={"content_type": "image/jpeg", "image_base64": _b64(PNG_BYTES)},
        headers=auth_headers(admin),
    )

    assert res.status_code == 400


def test_logo_upload_rejects_non_image_bytes(client, db_session, seed_permissions, monkeypatch):
    admin = _admin_with_settings_permission(db_session, "brand_garbage_admin")
    _stub_blob(monkeypatch)

    res = client.post(
        "/api/settings/logo",
        json={"content_type": "image/png", "image_base64": _b64(b"<script>alert(1)</script>")},
        headers=auth_headers(admin),
    )

    assert res.status_code == 400


def test_logo_upload_rejects_svg(client, db_session, seed_permissions):
    admin = _admin_with_settings_permission(db_session, "brand_svg_admin")

    res = client.post(
        "/api/settings/logo",
        json={"content_type": "image/svg+xml", "image_base64": _b64(b"<svg/>")},
        headers=auth_headers(admin),
    )

    assert res.status_code == 422


def test_logo_upload_requires_settings_permission(client, db_session, seed_permissions, monkeypatch):
    member = make_member(db_session, psn="BRAND-MEMBER", email="brand_member@example.com")
    member_user = make_member_user(db_session, member)
    _stub_blob(monkeypatch)

    res = client.post(
        "/api/settings/logo",
        json={"content_type": "image/png", "image_base64": _b64(PNG_BYTES)},
        headers=auth_headers(member_user),
    )

    assert res.status_code == 403


def test_logo_upload_reports_missing_storage_configuration(client, db_session, seed_permissions, monkeypatch):
    from app import blob_storage

    admin = _admin_with_settings_permission(db_session, "brand_nostore_admin")

    def not_configured(**kwargs):
        raise blob_storage.BlobNotConfigured("no token")

    monkeypatch.setattr(blob_storage, "upload_blob", not_configured)

    res = client.post(
        "/api/settings/logo",
        json={"content_type": "image/png", "image_base64": _b64(PNG_BYTES)},
        headers=auth_headers(admin),
    )

    assert res.status_code == 503


def test_replacing_a_logo_deletes_the_previous_blob(client, db_session, seed_permissions, monkeypatch):
    from app import blob_storage, models

    admin = _admin_with_settings_permission(db_session, "brand_replace_admin")
    deletes = []
    urls = iter(["https://blob.example.test/first.png", "https://blob.example.test/second.png"])

    def upload(pathname, data, content_type):
        return {"url": next(urls), "pathname": pathname}

    def delete(blob_url):
        deletes.append(blob_url)

    monkeypatch.setattr(blob_storage, "upload_blob", upload)
    monkeypatch.setattr(blob_storage, "delete_blob", delete)

    first = client.post(
        "/api/settings/logo",
        json={"content_type": "image/png", "image_base64": _b64(PNG_BYTES)},
        headers=auth_headers(admin),
    )
    second = client.post(
        "/api/settings/logo",
        json={"content_type": "image/jpeg", "image_base64": _b64(JPEG_BYTES)},
        headers=auth_headers(admin),
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["logo_url"] == "https://blob.example.test/second.png"
    assert deletes == ["https://blob.example.test/first.png"]
    assert db_session.query(models.Settings).first().logo_url == "https://blob.example.test/second.png"


def test_logo_removal_clears_the_stored_url_and_audits(client, db_session, seed_permissions, monkeypatch):
    from app import blob_storage, models

    admin = _admin_with_settings_permission(db_session, "brand_remove_admin")
    db_session.add(models.Settings(logo_url="https://blob.example.test/old.png"))
    db_session.commit()
    deletes = []
    monkeypatch.setattr(blob_storage, "delete_blob", lambda url: deletes.append(url))

    res = client.delete("/api/settings/logo", headers=auth_headers(admin))

    assert res.status_code == 200
    assert res.json()["logo_url"] is None
    assert deletes == ["https://blob.example.test/old.png"]

    event = (
        db_session.query(models.AuditEvent)
        .filter(models.AuditEvent.event_type == "settings.logo_removed")
        .first()
    )
    assert event is not None
    assert event.previous_values["logo_url"] == "https://blob.example.test/old.png"


def test_logo_removal_failure_keeps_the_record_pointing_at_the_blob(
    client, db_session, seed_permissions, monkeypatch
):
    from app import blob_storage, models

    admin = _admin_with_settings_permission(db_session, "brand_removefail_admin")
    db_session.add(models.Settings(logo_url="https://blob.example.test/stuck.png"))
    db_session.commit()

    def failing_delete(url):
        raise blob_storage.BlobOperationFailed("store unavailable")

    monkeypatch.setattr(blob_storage, "delete_blob", failing_delete)

    res = client.delete("/api/settings/logo", headers=auth_headers(admin))

    assert res.status_code == 502
    assert db_session.query(models.Settings).first().logo_url == "https://blob.example.test/stuck.png"
