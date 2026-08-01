"""Object storage infrastructure: S3-compatible port + MinIO adapter.

Buckets are tenant-partitioned by key prefix (`{tenant_id}/...`); bucket-per-
tenant is deliberately avoided at 1M-tenant scale.
"""

import io
import uuid
from datetime import timedelta
from typing import Protocol

import structlog

from platform_core.core.config import get_settings

log = structlog.get_logger("storage")

PLATFORM_BUCKET = "lacteva-platform"


class ObjectStorage(Protocol):
    async def put_object(self, key: str, data: bytes, content_type: str) -> str: ...
    async def presigned_get_url(self, key: str, expires_seconds: int = 900) -> str: ...


def tenant_key(tenant_id: uuid.UUID | None, name: str) -> str:
    return f"{tenant_id or 'platform'}/{name}"


class MinioObjectStorage:
    """MinIO/S3 adapter.

    The minio client is synchronous; calls are pushed to a thread so the event
    loop never blocks. TODO(M1): swap to an async S3 client or wrap with a
    bounded executor once upload volume grows.
    """

    def __init__(self) -> None:
        settings = get_settings()
        from minio import Minio

        self._client = Minio(
            settings.minio_endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=settings.minio_secure,
        )

    def _ensure_bucket(self) -> None:
        if not self._client.bucket_exists(PLATFORM_BUCKET):
            self._client.make_bucket(PLATFORM_BUCKET)

    async def put_object(self, key: str, data: bytes, content_type: str) -> str:
        import anyio

        def _put() -> None:
            self._ensure_bucket()
            self._client.put_object(
                PLATFORM_BUCKET, key, io.BytesIO(data), len(data), content_type=content_type
            )

        await anyio.to_thread.run_sync(_put)
        log.info("object_stored", key=key, size=len(data))
        return key

    async def presigned_get_url(self, key: str, expires_seconds: int = 900) -> str:
        import anyio

        def _url() -> str:
            return self._client.presigned_get_object(
                PLATFORM_BUCKET, key, expires=timedelta(seconds=expires_seconds)
            )

        return await anyio.to_thread.run_sync(_url)


class InMemoryObjectStorage:
    """Test adapter."""

    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    async def put_object(self, key: str, data: bytes, content_type: str) -> str:
        self.objects[key] = data
        return key

    async def presigned_get_url(self, key: str, expires_seconds: int = 900) -> str:
        return f"memory://{PLATFORM_BUCKET}/{key}"


_storage: ObjectStorage | None = None


def get_object_storage() -> ObjectStorage:
    global _storage
    if _storage is None:
        settings = get_settings()
        _storage = InMemoryObjectStorage() if settings.env == "test" else MinioObjectStorage()
    return _storage
