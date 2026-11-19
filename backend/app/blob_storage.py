"""
Minimal Vercel Blob client (upload + delete), shared by the branding
settings endpoints.

There is no official Python SDK, so this speaks the REST API the published
JavaScript SDK uses:

    PUT  {api}/?pathname=<pathname>
         authorization: Bearer <BLOB_READ_WRITE_TOKEN>
         x-api-version: 11
         x-content-type: <mime>
         x-add-random-suffix: 1
         body: raw bytes
         -> { url, downloadUrl, pathname, contentType, contentDisposition }

    POST {api}/delete
         body: { "urls": ["<blob url>"] }

The API version and defaults are copied from @vercel/blob v2.0.0; if a
future SDK revision changes the contract, this is the only file to touch.
The token is read per call (not imported once) so tests can monkeypatch the
environment.
"""
import logging
import os

import requests

logger = logging.getLogger("mact.blob")

DEFAULT_API_URL = "https://vercel.com/api/blob"
API_VERSION = "11"
REQUEST_TIMEOUT_SECONDS = 30


class BlobNotConfigured(RuntimeError):
    """No BLOB_READ_WRITE_TOKEN: logo storage cannot be used at all."""


class BlobOperationFailed(RuntimeError):
    """The Blob API rejected a request or was unreachable."""


def _token() -> str:
    return os.getenv("BLOB_READ_WRITE_TOKEN", "").strip()


def is_configured() -> bool:
    return bool(_token())


def _api_url() -> str:
    return os.getenv("VERCEL_BLOB_API_URL", "").strip() or DEFAULT_API_URL


def _headers(content_type: str) -> dict:
    return {
        "authorization": f"Bearer {_token()}",
        "x-api-version": API_VERSION,
        "content-type": content_type,
    }


def upload_blob(pathname: str, data: bytes, content_type: str) -> dict:
    if not is_configured():
        raise BlobNotConfigured("BLOB_READ_WRITE_TOKEN is not configured")

    try:
        response = requests.put(
            f"{_api_url()}/",
            params={"pathname": pathname},
            headers={**_headers(content_type), "x-add-random-suffix": "1"},
            data=data,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
    except requests.RequestException as exc:
        raise BlobOperationFailed(f"Could not reach the blob store: {exc}") from exc

    if response.status_code >= 400:
        raise BlobOperationFailed(
            f"Blob upload failed with status {response.status_code}: {response.text[:200]}"
        )

    payload = response.json()
    if not payload.get("url"):
        raise BlobOperationFailed("Blob upload response did not include a URL")
    return {"url": payload["url"], "pathname": payload.get("pathname")}


def delete_blob(url: str) -> None:
    """Best-effort deletion is *not* the policy here: callers decide whether
    a failure blocks the operation. A 404 counts as success (already gone)."""
    if not is_configured():
        raise BlobNotConfigured("BLOB_READ_WRITE_TOKEN is not configured")
    if not url:
        return

    try:
        response = requests.post(
            f"{_api_url()}/delete",
            json={"urls": [url]},
            headers=_headers("application/json"),
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
    except requests.RequestException as exc:
        raise BlobOperationFailed(f"Could not reach the blob store: {exc}") from exc

    if response.status_code >= 400 and response.status_code != 404:
        raise BlobOperationFailed(
            f"Blob delete failed with status {response.status_code}: {response.text[:200]}"
        )
