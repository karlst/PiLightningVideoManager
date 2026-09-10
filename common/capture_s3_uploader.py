"""S3 upload operations for classified V8 capture pairs."""

from __future__ import annotations

import json
from pathlib import Path

from common.aws_auth import AwsAuthConfig, AwsAuthenticator
from common.capture_key import canonical_capture_base_key, pair_keys
from common.s3_store import S3Store, S3StoreError
from common.sidecar_store import read_sidecar


def build_ingest_s3_store() -> S3Store:
    authenticator = AwsAuthenticator(AwsAuthConfig(profile_name="picam-ingest"))

    try:
        credential_document = json.loads(
            authenticator.credential_file.read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError(
            f"Unable to read AWS bucket configuration: {error}"
        ) from error

    bucket_name = str(credential_document.get("bucket", "") or "").strip()
    if not bucket_name:
        raise RuntimeError("AWS credential file is missing bucket name")

    return S3Store(bucket_name, authenticator)


def upload_capture_pair_to_s3(
    store: S3Store,
    video_path: Path,
    sidecar_path: Path,
) -> str:
    """Upload MP4 then JSON; roll back the MP4 if the JSON upload fails."""
    sidecar = read_sidecar(sidecar_path)
    base_key = canonical_capture_base_key(
        sidecar,
        fallback_stem=video_path.stem,
    )
    mp4_key, json_key = pair_keys(base_key)

    try:
        store.upload_file(video_path, mp4_key)
    except (OSError, S3StoreError) as error:
        raise S3StoreError(f"MP4 upload failed: {error}") from error

    try:
        store.upload_file(sidecar_path, json_key)
    except (OSError, S3StoreError) as error:
        rollback_error = ""
        try:
            store.delete_object(mp4_key)
        except Exception as cleanup_error:
            rollback_error = f"; rollback failed for {mp4_key}: {cleanup_error}"
        raise S3StoreError(
            f"JSON upload failed: {error}{rollback_error}"
        ) from error

    return base_key
