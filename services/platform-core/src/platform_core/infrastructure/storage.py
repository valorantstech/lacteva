"""Object storage infrastructure: S3-compatible port + MinIO adapter.

Buckets are tenant-partitioned by key prefix (`{tenant_id}/...`); bucket-per-
tenant is deliberately avoided at 1M-tenant scale.
"""

import io
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol

import structlog

from platform_core.core.config import get_settings

log = structlog.get_logger("storage")

PLATFORM_BUCKET = "lacteva-platform"


class ObjectStorage(Protocol):
    async def put_object(self, key: str, data: bytes, content_type: str) -> str: ...
    async def presigned_get_url(self, key: str, expires_seconds: int = 900) -> str: ...

    # BKP-003 added the read side. The port was write-only — enough for
    # supplier documents, which are uploaded and then served by presigned URL,
    # and not enough for a backup, which has to be READ BACK to be worth
    # anything. Off-site replication needs all four: `get` to restore, `stat`
    # to verify an upload landed whole, `list` to apply retention, and
    # `delete` to enforce it.
    async def get_object(self, key: str) -> bytes: ...
    async def stat_object(self, key: str) -> "ObjectInfo | None": ...
    async def list_objects(self, prefix: str) -> "list[ObjectInfo]": ...
    async def delete_object(self, key: str) -> None: ...


@dataclass(frozen=True)
class ObjectInfo:
    """What the store knows about an object without reading it."""

    key: str
    size: int
    #: The store's own modification time. Retention orders by the manifest's
    #: `created_at` instead — a clock on the storage side is not the clock the
    #: backup was taken by, and ordering backups by the wrong one is how the
    #: newest gets pruned.
    last_modified: "datetime | None" = None


def tenant_key(tenant_id: uuid.UUID | None, name: str) -> str:
    return f"{tenant_id or 'platform'}/{name}"


class MinioObjectStorage:
    """MinIO/S3 adapter.

    The minio client is synchronous; calls are pushed to a thread so the event
    loop never blocks. TODO(M1): swap to an async S3 client or wrap with a
    bounded executor once upload volume grows.
    """

    def __init__(
        self,
        *,
        endpoint: str | None = None,
        access_key: str | None = None,
        secret_key: str | None = None,
        secure: bool | None = None,
        bucket: str = PLATFORM_BUCKET,
    ) -> None:
        """Endpoint and credentials are parameters, not settings lookups.

        BKP-003: a backup's whole purpose is to survive the loss of the system
        it came from, so it must be able to live on a DIFFERENT endpoint with
        DIFFERENT credentials from the application's own object storage. The
        defaults keep every existing caller working unchanged.
        """
        settings = get_settings()
        from minio import Minio

        self._bucket = bucket
        self._client = Minio(
            endpoint or settings.minio_endpoint,
            access_key=access_key or settings.minio_access_key,
            secret_key=secret_key or settings.minio_secret_key,
            secure=settings.minio_secure if secure is None else secure,
        )

    def _ensure_bucket(self) -> None:
        if not self._client.bucket_exists(self._bucket):
            self._client.make_bucket(self._bucket)

    async def put_object(self, key: str, data: bytes, content_type: str) -> str:
        import anyio

        def _put() -> None:
            self._ensure_bucket()
            self._client.put_object(
                self._bucket, key, io.BytesIO(data), len(data), content_type=content_type
            )

        await anyio.to_thread.run_sync(_put)
        log.info("object_stored", key=key, size=len(data))
        return key

    async def presigned_get_url(self, key: str, expires_seconds: int = 900) -> str:
        import anyio

        def _url() -> str:
            return self._client.presigned_get_object(
                self._bucket, key, expires=timedelta(seconds=expires_seconds)
            )

        return await anyio.to_thread.run_sync(_url)

    async def get_object(self, key: str) -> bytes:
        import anyio

        def _get() -> bytes:
            response = self._client.get_object(self._bucket, key)
            try:
                return response.read()
            finally:
                response.close()
                response.release_conn()

        return await anyio.to_thread.run_sync(_get)

    async def stat_object(self, key: str) -> ObjectInfo | None:
        import anyio
        from minio.error import S3Error

        def _stat() -> ObjectInfo | None:
            try:
                info = self._client.stat_object(self._bucket, key)
            except S3Error as exc:
                # `NoSuchBucket` matters as much as `NoSuchKey`: the FIRST
                # thing off-site replication does is ask whether a backup id is
                # already taken, and on a brand-new destination the bucket does
                # not exist yet. Treating that as an error made the very first
                # replication to a fresh store fail — found by running it.
                if exc.code in ("NoSuchKey", "NoSuchObject", "NotFound", "NoSuchBucket"):
                    return None
                raise
            return ObjectInfo(key=key, size=info.size, last_modified=info.last_modified)

        return await anyio.to_thread.run_sync(_stat)

    async def list_objects(self, prefix: str) -> list[ObjectInfo]:
        import anyio

        def _list() -> list[ObjectInfo]:
            if not self._client.bucket_exists(self._bucket):
                return []  # nothing has ever been stored here
            return [
                ObjectInfo(key=o.object_name, size=o.size or 0, last_modified=o.last_modified)
                for o in self._client.list_objects(self._bucket, prefix=prefix, recursive=True)
            ]

        return await anyio.to_thread.run_sync(_list)

    async def delete_object(self, key: str) -> None:
        import anyio

        def _delete() -> None:
            self._client.remove_object(self._bucket, key)

        await anyio.to_thread.run_sync(_delete)
        log.info("object_deleted", key=key, bucket=self._bucket)


class InMemoryObjectStorage:
    """Test adapter."""

    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        #: Set to raise on the next put — used to prove that a failed upload is
        #: never recorded as a successful backup.
        self.fail_next_put: Exception | None = None

    async def put_object(self, key: str, data: bytes, content_type: str) -> str:
        if self.fail_next_put is not None:
            error, self.fail_next_put = self.fail_next_put, None
            raise error
        self.objects[key] = data
        return key

    async def presigned_get_url(self, key: str, expires_seconds: int = 900) -> str:
        return f"memory://{PLATFORM_BUCKET}/{key}"

    async def get_object(self, key: str) -> bytes:
        if key not in self.objects:
            raise KeyError(key)
        return self.objects[key]

    async def stat_object(self, key: str) -> ObjectInfo | None:
        if key not in self.objects:
            return None
        return ObjectInfo(key=key, size=len(self.objects[key]))

    async def list_objects(self, prefix: str) -> list[ObjectInfo]:
        return [
            ObjectInfo(key=k, size=len(v))
            for k, v in sorted(self.objects.items())
            if k.startswith(prefix)
        ]

    async def delete_object(self, key: str) -> None:
        self.objects.pop(key, None)


_storage: ObjectStorage | None = None


def get_object_storage() -> ObjectStorage:
    global _storage
    if _storage is None:
        settings = get_settings()
        _storage = InMemoryObjectStorage() if settings.env == "test" else MinioObjectStorage()
    return _storage
