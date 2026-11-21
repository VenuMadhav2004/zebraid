"""Server-side client for the private Supabase Storage bucket.

Uses the service-role key, which must only ever be loaded on the backend.
No public URLs are produced: reads go through authenticated download or
short-lived signed URLs.
"""
from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

import httpx

from app.core.config import Settings, get_settings
from app.models.enums import ImageKind

ALLOWED_IMAGE_TYPES: dict[str, str] = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}
_SAFE_PREFIX = re.compile(r"^[A-Za-z0-9_\-]+(/[A-Za-z0-9_\-]+)*$")


class StorageError(Exception):
    """Storage API failure. Messages never include credentials."""

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


class StorageConflictError(StorageError):
    """Object already exists at that path (uploads never overwrite)."""


class StorageNotFoundError(StorageError):
    pass


class ImageValidationError(ValueError):
    """Content is empty, corrupt or does not match its declared type."""


class ImageTooLargeError(ImageValidationError):
    pass


class UnsupportedImageTypeError(ImageValidationError):
    pass


def sniff_image_type(content: bytes) -> str | None:
    """Detect the real format from magic bytes (the declared type is not trusted)."""
    if content[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if content[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if len(content) >= 12 and content[:4] == b"RIFF" and content[8:12] == b"WEBP":
        return "image/webp"
    return None


def validate_image(content: bytes, declared_type: str, *, max_bytes: int) -> str:
    """Return the validated MIME type or raise ImageValidationError."""
    if not content:
        raise ImageValidationError("empty file")
    if len(content) > max_bytes:
        raise ImageTooLargeError(f"file exceeds {max_bytes} bytes")
    declared = (declared_type or "").split(";")[0].strip().lower()
    if declared not in ALLOWED_IMAGE_TYPES:
        raise UnsupportedImageTypeError(f"unsupported content type {declared or '(none)'}")
    actual = sniff_image_type(content)
    if actual is None:
        raise UnsupportedImageTypeError("file content is not JPEG, PNG or WebP")
    if actual != declared:
        raise ImageValidationError(f"content does not match declared type {declared}")
    return declared


def generate_storage_path(kind: ImageKind, content_type: str, *, prefix: str | None = None, now: datetime | None = None) -> str:
    """Server-generated, collision-resistant key. No user input reaches the path."""
    if content_type not in ALLOWED_IMAGE_TYPES:
        raise ImageValidationError(f"unsupported content type {content_type}")
    if prefix is not None and not _SAFE_PREFIX.match(prefix):
        raise ValueError("prefix may only contain letters, digits, '_', '-' and '/' separators")
    now = now or datetime.now(timezone.utc)
    key = f"{kind.value}/{now:%Y/%m}/{uuid.uuid4().hex}{ALLOWED_IMAGE_TYPES[content_type]}"
    return f"{prefix}/{key}" if prefix else key


@dataclass(frozen=True)
class SignedUrl:
    url: str
    expires_in: int
    expires_at: datetime  # informational; access ends here, never treat as permanent


class SupabaseStorage:
    def __init__(
        self,
        *,
        base_url: str,
        service_key: str,
        bucket: str,
        max_upload_bytes: int,
        default_ttl: int = 60,
        max_ttl: int = 3600,
        client: httpx.Client | None = None,
    ):
        if not base_url or not service_key:
            raise StorageError("Supabase Storage is not configured")
        self.bucket = bucket
        self.max_upload_bytes = max_upload_bytes
        self.default_ttl = default_ttl
        self.max_ttl = max_ttl
        self._api = base_url.rstrip("/") + "/storage/v1"
        self._client = client or httpx.Client(timeout=30)
        self._headers = {"Authorization": f"Bearer {service_key}", "apikey": service_key}

    @classmethod
    def from_settings(cls, settings: Settings | None = None, client: httpx.Client | None = None) -> "SupabaseStorage":
        s = settings or get_settings()
        return cls(
            base_url=s.supabase_url,
            service_key=s.supabase_service_role_key.strip(),
            bucket=s.supabase_storage_bucket,
            max_upload_bytes=s.storage_max_upload_bytes,
            default_ttl=s.storage_signed_url_default_ttl,
            max_ttl=s.storage_signed_url_max_ttl,
            client=client,
        )

    # -- helpers -----------------------------------------------------------
    def _obj(self, path: str) -> str:
        return f"{quote(self.bucket)}/{quote(path, safe='/')}"

    def _request(self, method: str, url: str, **kw) -> httpx.Response:
        headers = {**self._headers, **kw.pop("headers", {})}
        try:
            resp = self._client.request(method, self._api + url, headers=headers, **kw)
        except httpx.HTTPError as exc:
            raise StorageError(f"storage request failed: {type(exc).__name__}") from None
        if resp.status_code < 400:
            return resp
        try:
            body = resp.json()
        except ValueError:
            body = {}
        message = str(body.get("message") or body.get("error") or resp.reason_phrase)[:200]
        code = str(body.get("statusCode", resp.status_code))
        if code == "409" or "duplicate" in message.lower() or "already exists" in message.lower():
            raise StorageConflictError(message, resp.status_code)
        if code == "404" or "not found" in message.lower():
            raise StorageNotFoundError(message, resp.status_code)
        raise StorageError(message, resp.status_code)

    # -- bucket ------------------------------------------------------------
    def get_bucket(self) -> dict:
        return self._request("GET", f"/bucket/{quote(self.bucket)}").json()

    # -- objects -----------------------------------------------------------
    def upload(self, path: str, content: bytes, content_type: str) -> None:
        """Validate then upload. Never overwrites (x-upsert: false)."""
        content_type = validate_image(content, content_type, max_bytes=self.max_upload_bytes)
        self._request(
            "POST",
            f"/object/{self._obj(path)}",
            content=content,
            headers={"Content-Type": content_type, "x-upsert": "false", "Cache-Control": "no-store"},
        )

    def download(self, path: str) -> bytes:
        return self._request("GET", f"/object/authenticated/{self._obj(path)}").content

    def delete(self, paths: list[str]) -> list[str]:
        """Returns the paths Storage actually removed."""
        if not paths:
            return []
        resp = self._request("DELETE", f"/object/{quote(self.bucket)}", json={"prefixes": list(paths)})
        return [o.get("name") for o in resp.json()]

    def list(self, prefix: str, limit: int = 100) -> list[dict]:
        resp = self._request("POST", f"/object/list/{quote(self.bucket)}", json={"prefix": prefix, "limit": limit})
        return resp.json()

    def _ttl(self, expires_in: int | None) -> int:
        ttl = self.default_ttl if expires_in is None else int(expires_in)
        if not 1 <= ttl <= self.max_ttl:
            raise ValueError(f"expires_in must be between 1 and {self.max_ttl} seconds")
        return ttl

    def signed_urls(self, paths: list[str], expires_in: int | None = None) -> dict[str, SignedUrl | None]:
        """Sign many objects in one request. Missing objects map to None."""
        ttl = self._ttl(expires_in)
        if not paths:
            return {}
        data = self._request("POST", f"/object/sign/{quote(self.bucket)}", json={"expiresIn": ttl, "paths": list(paths)}).json()
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=ttl)
        result: dict[str, SignedUrl | None] = dict.fromkeys(paths)
        for item in data:
            signed = item.get("signedURL") or item.get("signedUrl")
            if item.get("path") in result and signed and not item.get("error"):
                result[item["path"]] = SignedUrl(url=self._api + signed, expires_in=ttl, expires_at=expires_at)
        return result

    def signed_url(self, path: str, expires_in: int | None = None) -> SignedUrl:
        ttl = self._ttl(expires_in)
        data = self._request("POST", f"/object/sign/{self._obj(path)}", json={"expiresIn": ttl}).json()
        signed = data.get("signedURL") or data.get("signedUrl")
        if not signed:
            raise StorageError("storage did not return a signed URL")
        return SignedUrl(
            url=self._api + signed,
            expires_in=ttl,
            expires_at=datetime.now(timezone.utc) + timedelta(seconds=ttl),
        )
