"""Small reusable S3 object-store interface for Pi Camera Capture."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from botocore.exceptions import ClientError, BotoCoreError

from common.aws_auth import AwsAuthenticator


class S3StoreError(Exception):
    """Base exception raised by S3Store."""


class S3ObjectNotFoundError(S3StoreError):
    """Requested S3 object does not exist."""


class S3AccessDeniedError(S3StoreError):
    """AWS denied the requested S3 operation."""


@dataclass(frozen=True)
class S3ObjectInfo:
    key: str
    size: int
    last_modified: datetime | None
    etag: str | None = None


class S3Store:
    """Generic object operations for one S3 bucket.

    This class intentionally knows nothing about lightning classification,
    capture sidecars, workflow state, or how credentials are stored.
    """

    def __init__(
        self,
        bucket_name: str,
        authenticator: AwsAuthenticator | None = None,
        *,
        client: Any | None = None,
    ) -> None:
        if not bucket_name or not bucket_name.strip():
            raise ValueError("bucket_name must not be empty")
        if client is None and authenticator is None:
            raise ValueError("authenticator or client is required")

        self._bucket_name = bucket_name.strip()
        self._client = client if client is not None else authenticator.create_s3_client()

    @property
    def bucket_name(self) -> str:
        return self._bucket_name

    def list_objects(self, prefix: str = "") -> list[S3ObjectInfo]:
        """Return all objects matching prefix, transparently handling pagination."""
        objects: list[S3ObjectInfo] = []
        kwargs: dict[str, Any] = {"Bucket": self.bucket_name, "Prefix": prefix}

        try:
            while True:
                response = self._client.list_objects_v2(**kwargs)
                for item in response.get("Contents", []):
                    objects.append(
                        S3ObjectInfo(
                            key=item["Key"],
                            size=int(item.get("Size", 0)),
                            last_modified=item.get("LastModified"),
                            etag=self._strip_etag(item.get("ETag")),
                        )
                    )

                token = response.get("NextContinuationToken")
                if not response.get("IsTruncated") or not token:
                    break
                kwargs["ContinuationToken"] = token
        except (ClientError, BotoCoreError) as exc:
            self._raise_translated(exc, f"list objects under '{prefix}'")

        return objects

    def object_exists(self, key: str) -> bool:
        """Return True if key exists; return False only for a real not-found response."""
        try:
            self._client.head_object(Bucket=self.bucket_name, Key=key)
            return True
        except ClientError as exc:
            code = self._error_code(exc)
            if code in {"404", "NoSuchKey", "NotFound"}:
                return False
            self._raise_translated(exc, f"check object '{key}'")
        except BotoCoreError as exc:
            self._raise_translated(exc, f"check object '{key}'")
        return False

    def upload_file(self, local_path: str | Path, key: str) -> None:
        path = Path(local_path)
        if not path.is_file():
            raise FileNotFoundError(path)

        try:
            self._client.upload_file(str(path), self.bucket_name, key)
        except (ClientError, BotoCoreError) as exc:
            self._raise_translated(exc, f"upload '{path}' to '{key}'")

    def download_file(self, key: str, local_path: str | Path) -> Path:
        path = Path(local_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        try:
            self._client.download_file(self.bucket_name, key, str(path))
        except (ClientError, BotoCoreError) as exc:
            self._raise_translated(exc, f"download '{key}'")

        return path

    def upload_bytes(self, data: bytes, key: str, content_type: str | None = None) -> None:
        kwargs: dict[str, Any] = {
            "Bucket": self.bucket_name,
            "Key": key,
            "Body": data,
        }
        if content_type:
            kwargs["ContentType"] = content_type

        try:
            self._client.put_object(**kwargs)
        except (ClientError, BotoCoreError) as exc:
            self._raise_translated(exc, f"upload bytes to '{key}'")

    def download_bytes(self, key: str) -> bytes:
        try:
            response = self._client.get_object(Bucket=self.bucket_name, Key=key)
            return response["Body"].read()
        except (ClientError, BotoCoreError) as exc:
            self._raise_translated(exc, f"download bytes from '{key}'")
        raise AssertionError("unreachable")

    def delete_object(self, key: str) -> None:
        try:
            self._client.delete_object(Bucket=self.bucket_name, Key=key)
        except (ClientError, BotoCoreError) as exc:
            self._raise_translated(exc, f"delete '{key}'")

    def copy_object(self, source_key: str, destination_key: str) -> None:
        copy_source = {"Bucket": self.bucket_name, "Key": source_key}
        try:
            self._client.copy_object(
                Bucket=self.bucket_name,
                Key=destination_key,
                CopySource=copy_source,
            )
        except (ClientError, BotoCoreError) as exc:
            self._raise_translated(
                exc, f"copy '{source_key}' to '{destination_key}'"
            )

    def move_object(self, source_key: str, destination_key: str) -> None:
        """Copy, verify destination, then delete source.

        Source is never deleted unless the destination can be HEADed successfully.
        """
        self.copy_object(source_key, destination_key)
        if not self.object_exists(destination_key):
            raise S3StoreError(
                f"S3 move verification failed: destination does not exist: {destination_key}"
            )
        self.delete_object(source_key)

    @staticmethod
    def _strip_etag(value: Any) -> str | None:
        if not isinstance(value, str):
            return None
        return value.strip('"')

    @staticmethod
    def _error_code(exc: ClientError) -> str:
        return str(exc.response.get("Error", {}).get("Code", ""))

    def _raise_translated(self, exc: Exception, operation: str) -> None:
        if isinstance(exc, ClientError):
            code = self._error_code(exc)
            message = str(exc.response.get("Error", {}).get("Message", ""))
            if code in {"403", "AccessDenied", "Forbidden"}:
                raise S3AccessDeniedError(
                    f"Access denied while attempting to {operation}: {message or code}"
                ) from exc
            if code in {"404", "NoSuchKey", "NotFound"}:
                raise S3ObjectNotFoundError(
                    f"S3 object not found while attempting to {operation}"
                ) from exc
            raise S3StoreError(
                f"S3 error while attempting to {operation}: {code}: {message}"
            ) from exc

        raise S3StoreError(f"AWS error while attempting to {operation}: {exc}") from exc
