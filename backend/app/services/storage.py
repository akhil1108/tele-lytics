"""Blob storage for call recordings.

Local disk by default so the stack runs with no cloud account; S3 (or any
S3-compatible endpoint) in deployment. Keys are content-addressed by call so a
re-upload of the same call overwrites rather than accumulating.
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import re
import shutil
from abc import ABC, abstractmethod
from datetime import UTC, datetime
from pathlib import Path

from app.core.config import settings
from app.core.errors import NotFound
from app.core.logging import get_logger

log = get_logger(__name__)

_EXTENSIONS = {
    "audio/mp4": ".m4a", "audio/m4a": ".m4a", "audio/x-m4a": ".m4a",
    "audio/mpeg": ".mp3", "audio/mp3": ".mp3", "audio/wav": ".wav",
    "audio/x-wav": ".wav", "audio/wave": ".wav", "audio/ogg": ".ogg",
    "audio/opus": ".opus", "audio/webm": ".webm", "audio/aac": ".aac",
    "audio/amr": ".amr", "audio/3gpp": ".3gp", "audio/flac": ".flac",
}

SUPPORTED_MIME_TYPES = frozenset(_EXTENSIONS)
_SAFE_KEY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9/_.\-]*$")


def extension_for(mime_type: str) -> str:
    return _EXTENSIONS.get(mime_type.split(";")[0].strip().lower(), ".bin")


def build_key(org_id: str, call_id: str, mime_type: str) -> str:
    """`recordings/<org>/<yyyy>/<mm>/<call>.<ext>` — date-partitioned so
    lifecycle rules and manual pruning can work on prefixes."""
    now = datetime.now(UTC)
    return f"recordings/{org_id}/{now:%Y/%m}/{call_id}{extension_for(mime_type)}"


def checksum(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class StorageBackend(ABC):
    name: str

    @abstractmethod
    async def put(self, key: str, data: bytes, content_type: str) -> None: ...

    @abstractmethod
    async def get(self, key: str) -> bytes: ...

    @abstractmethod
    async def delete(self, key: str) -> None: ...

    @abstractmethod
    async def exists(self, key: str) -> bool: ...


class LocalStorage(StorageBackend):
    name = "local"

    def __init__(self, root: str | None = None) -> None:
        self.root = Path(root or settings.storage_local_path).expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        if not _SAFE_KEY.match(key) or ".." in key:
            raise ValueError(f"unsafe storage key: {key!r}")
        path = (self.root / key).resolve()
        # Belt and braces: even with a validated key, never escape the root.
        if not path.is_relative_to(self.root):
            raise ValueError(f"storage key escapes root: {key!r}")
        return path

    async def put(self, key: str, data: bytes, content_type: str) -> None:
        path = self._path(key)

        def _write() -> None:
            path.parent.mkdir(parents=True, exist_ok=True)
            # Write to a sibling temp file and rename, so a crash mid-write
            # never leaves a truncated recording that looks complete.
            tmp = path.with_suffix(path.suffix + ".part")
            tmp.write_bytes(data)
            os.replace(tmp, path)

        await asyncio.to_thread(_write)

    async def get(self, key: str) -> bytes:
        path = self._path(key)
        if not path.exists():
            raise NotFound("Recording file")
        return await asyncio.to_thread(path.read_bytes)

    async def delete(self, key: str) -> None:
        path = self._path(key)
        await asyncio.to_thread(lambda: path.unlink(missing_ok=True))

    async def exists(self, key: str) -> bool:
        return await asyncio.to_thread(self._path(key).exists)

    def usage_bytes(self) -> int:
        return sum(f.stat().st_size for f in self.root.rglob("*") if f.is_file())

    def free_bytes(self) -> int:
        return shutil.disk_usage(self.root).free


class S3Storage(StorageBackend):
    name = "s3"

    def __init__(self) -> None:
        try:
            import boto3
        except ImportError as exc:  # pragma: no cover - depends on optional extra
            raise RuntimeError(
                "STORAGE_BACKEND=s3 requires the s3 extra: pip install '.[s3]'"
            ) from exc
        if not settings.s3_bucket:
            raise RuntimeError("STORAGE_BACKEND=s3 requires S3_BUCKET")

        self.bucket = settings.s3_bucket
        self._client = boto3.client(
            "s3",
            region_name=settings.s3_region,
            endpoint_url=settings.s3_endpoint_url,
        )

    async def put(self, key: str, data: bytes, content_type: str) -> None:
        await asyncio.to_thread(
            self._client.put_object,
            Bucket=self.bucket,
            Key=key,
            Body=data,
            ContentType=content_type,
        )

    async def get(self, key: str) -> bytes:
        def _read() -> bytes:
            try:
                response = self._client.get_object(Bucket=self.bucket, Key=key)
            except self._client.exceptions.NoSuchKey as exc:
                raise NotFound("Recording file") from exc
            return response["Body"].read()

        return await asyncio.to_thread(_read)

    async def delete(self, key: str) -> None:
        await asyncio.to_thread(self._client.delete_object, Bucket=self.bucket, Key=key)

    async def exists(self, key: str) -> bool:
        def _head() -> bool:
            try:
                self._client.head_object(Bucket=self.bucket, Key=key)
            except Exception:
                return False
            return True

        return await asyncio.to_thread(_head)


_backend: StorageBackend | None = None


def get_storage() -> StorageBackend:
    global _backend
    if _backend is None:
        _backend = S3Storage() if settings.storage_backend == "s3" else LocalStorage()
        log.info("storage backend selected", extra={"backend": _backend.name})
    return _backend


def reset_storage() -> None:
    """Drop the cached backend. Used by tests."""
    global _backend
    _backend = None
