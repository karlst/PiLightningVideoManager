#!/usr/bin/env python3
"""Standalone CLI/integration test for Pi Camera S3 access.

Examples:
  python tools/test_s3.py list --profile picam-manager unverified/
  python tools/test_s3.py upload --profile picam-manager local.mp4 unverified/local.mp4
  python tools/test_s3.py self-test --profile picam-manager
  python tools/test_s3.py ingest-test --profile picam-ingest

The self-test writes only under test/<uuid>/ and cleans up after itself.
The ingest-test writes only under unverified/test/<uuid>/ and deliberately
verifies that DeleteObject and writes outside unverified/ are denied.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import uuid

# Allow direct execution from the project root without installation.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from common.aws_auth import AwsAuthConfig, AwsAuthenticator, DEFAULT_CREDENTIAL_FILE
from common.s3_store import S3AccessDeniedError, S3Store, S3StoreError


DEFAULT_BUCKET = "soloran-picam"


def build_store(args: argparse.Namespace) -> S3Store:
    auth = AwsAuthenticator(
        AwsAuthConfig(
            profile_name=args.profile,
            credential_file=Path(args.credentials).expanduser(),
            region=args.region,
        )
    )
    return S3Store(args.bucket, auth)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while True:
            chunk = stream.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def cmd_list(store: S3Store, args: argparse.Namespace) -> None:
    objects = store.list_objects(args.prefix)
    for obj in objects:
        when = obj.last_modified.isoformat() if obj.last_modified else ""
        print(f"{obj.size:10d}  {when:25s}  {obj.key}")
    print(f"{len(objects)} object(s)")


def cmd_exists(store: S3Store, args: argparse.Namespace) -> None:
    exists = store.object_exists(args.key)
    print("YES" if exists else "NO")
    raise SystemExit(0 if exists else 1)


def cmd_upload(store: S3Store, args: argparse.Namespace) -> None:
    store.upload_file(args.local_path, args.key)
    print(f"Uploaded {args.local_path} -> s3://{store.bucket_name}/{args.key}")


def cmd_download(store: S3Store, args: argparse.Namespace) -> None:
    path = store.download_file(args.key, args.local_path)
    print(f"Downloaded s3://{store.bucket_name}/{args.key} -> {path}")


def cmd_delete(store: S3Store, args: argparse.Namespace) -> None:
    store.delete_object(args.key)
    print(f"Deleted s3://{store.bucket_name}/{args.key}")


def cmd_copy(store: S3Store, args: argparse.Namespace) -> None:
    store.copy_object(args.source_key, args.destination_key)
    print(f"Copied {args.source_key} -> {args.destination_key}")


def cmd_move(store: S3Store, args: argparse.Namespace) -> None:
    store.move_object(args.source_key, args.destination_key)
    print(f"Moved {args.source_key} -> {args.destination_key}")


def cmd_self_test(store: S3Store, args: argparse.Namespace) -> None:
    test_id = uuid.uuid4().hex
    prefix = f"test/{test_id}"
    key_a = f"{prefix}/source.txt"
    key_b = f"{prefix}/copy.txt"
    key_c = f"{prefix}/moved.txt"
    payload = f"Pi Camera S3 integration test {test_id}\n".encode("utf-8")

    print(f"Bucket:  {store.bucket_name}")
    print(f"Profile: {args.profile}")
    print(f"Prefix:  {prefix}/")

    cleanup_keys = {key_a, key_b, key_c}
    try:
        print("1. upload bytes")
        store.upload_bytes(payload, key_a, content_type="text/plain")

        print("2. verify exists")
        assert store.object_exists(key_a)

        print("3. list prefix")
        listed = {obj.key for obj in store.list_objects(prefix)}
        assert key_a in listed

        print("4. download bytes and compare")
        assert store.download_bytes(key_a) == payload

        print("5. copy")
        store.copy_object(key_a, key_b)
        assert store.object_exists(key_b)

        print("6. move copied object")
        store.move_object(key_b, key_c)
        assert not store.object_exists(key_b)
        assert store.object_exists(key_c)

        print("7. download to local file and verify")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "downloaded.txt"
            store.download_file(key_c, path)
            assert path.read_bytes() == payload

        print("PASS: full manager S3 integration test")
    finally:
        print("8. cleanup")
        for key in cleanup_keys:
            try:
                if store.object_exists(key):
                    store.delete_object(key)
            except S3StoreError as exc:
                print(f"WARNING: cleanup failed for {key}: {exc}", file=sys.stderr)


def cmd_ingest_test(store: S3Store, args: argparse.Namespace) -> None:
    test_id = uuid.uuid4().hex
    allowed_key = f"unverified/test/{test_id}/ingest.txt"
    denied_key = f"reviewed/test/{test_id}/should-not-write.txt"
    payload = f"Pi Camera ingest permission test {test_id}\n".encode("utf-8")

    print(f"Bucket:  {store.bucket_name}")
    print(f"Profile: {args.profile}")

    print("1. upload under unverified/ (must PASS)")
    store.upload_bytes(payload, allowed_key, content_type="text/plain")

    print("2. list under unverified/ (must PASS)")
    listed = {obj.key for obj in store.list_objects(f"unverified/test/{test_id}")}
    assert allowed_key in listed

    print("3. read object (must PASS)")
    assert store.download_bytes(allowed_key) == payload

    print("4. delete object (must be DENIED)")
    try:
        store.delete_object(allowed_key)
    except S3AccessDeniedError:
        print("   expected AccessDenied")
    else:
        raise AssertionError("picam-ingest unexpectedly has DeleteObject permission")

    print("5. write outside unverified/ (must be DENIED)")
    try:
        store.upload_bytes(payload, denied_key)
    except S3AccessDeniedError:
        print("   expected AccessDenied")
    else:
        raise AssertionError("picam-ingest unexpectedly wrote outside unverified/")

    print("PASS: ingest IAM permissions behave as expected")
    print("NOTE: ingest cannot delete its test object; remove it later with picam-manager:")
    print(f"  {allowed_key}")


def make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Pi Camera S3 test utility")
    parser.add_argument("--profile", default="picam-manager")
    parser.add_argument("--credentials", default=str(DEFAULT_CREDENTIAL_FILE))
    parser.add_argument("--bucket", default=DEFAULT_BUCKET)
    parser.add_argument("--region", default=None, help="Override region from credential file")

    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("list")
    p.add_argument("prefix", nargs="?", default="")
    p.set_defaults(func=cmd_list)

    p = sub.add_parser("exists")
    p.add_argument("key")
    p.set_defaults(func=cmd_exists)

    p = sub.add_parser("upload")
    p.add_argument("local_path")
    p.add_argument("key")
    p.set_defaults(func=cmd_upload)

    p = sub.add_parser("download")
    p.add_argument("key")
    p.add_argument("local_path")
    p.set_defaults(func=cmd_download)

    p = sub.add_parser("delete")
    p.add_argument("key")
    p.set_defaults(func=cmd_delete)

    p = sub.add_parser("copy")
    p.add_argument("source_key")
    p.add_argument("destination_key")
    p.set_defaults(func=cmd_copy)

    p = sub.add_parser("move")
    p.add_argument("source_key")
    p.add_argument("destination_key")
    p.set_defaults(func=cmd_move)

    p = sub.add_parser("self-test")
    p.set_defaults(func=cmd_self_test)

    p = sub.add_parser("ingest-test")
    p.set_defaults(func=cmd_ingest_test)

    return parser


def main() -> int:
    parser = make_parser()
    args = parser.parse_args()
    try:
        store = build_store(args)
        args.func(store, args)
        return 0
    except (S3StoreError, OSError, ValueError, AssertionError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
