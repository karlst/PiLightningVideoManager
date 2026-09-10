#!/usr/bin/env python3
"""
Download every JSON sidecar under the S3 verified/ namespace.

Usage:
    python download_verified_sidecars.py OUTPUT_FOLDER

Example:
    python download_verified_sidecars.py C:\\temp\\verified_sidecars

By default this uses:
    ~/.picam/aws_credentials.json
profile:
    picam-manager

The verified/ prefix is stripped locally, but the remaining S3 directory
structure is preserved to avoid filename collisions.
"""

from __future__ import annotations

import argparse
from pathlib import Path, PurePosixPath
import sys

from common.aws_auth import AwsAuthConfig, AwsAuthenticator, AwsAuthError
from common.s3_store import S3Store, S3StoreError


DEFAULT_PROFILE = "picam-manager"
VERIFIED_PREFIX = "verified/"


def download_verified_sidecars(
    output_directory: Path,
    profile_name: str = DEFAULT_PROFILE,
) -> tuple[int, int]:
    output_directory = output_directory.expanduser().resolve()
    output_directory.mkdir(parents=True, exist_ok=True)

    authenticator = AwsAuthenticator(
        AwsAuthConfig(profile_name=profile_name)
    )

    store = S3Store(
        authenticator.bucket_name,
        authenticator,
    )

    objects = store.list_objects(VERIFIED_PREFIX)

    json_objects = [
        obj
        for obj in objects
        if obj.key.lower().endswith(".json")
    ]

    downloaded = 0
    failed = 0

    print(f"Bucket: {store.bucket_name}")
    print(f"Profile: {profile_name}")
    print(f"Verified JSON sidecars found: {len(json_objects)}")
    print(f"Destination: {output_directory}")
    print()

    for index, obj in enumerate(json_objects, start=1):
        key_path = PurePosixPath(obj.key)

        try:
            relative_parts = key_path.parts[1:]

            if not relative_parts:
                raise RuntimeError(
                    f"Invalid verified object key: {obj.key}"
                )

            local_path = output_directory.joinpath(*relative_parts)

            store.download_file(
                obj.key,
                local_path,
            )

            downloaded += 1

            print(
                f"[{index}/{len(json_objects)}] "
                f"{obj.key} -> {local_path}"
            )

        except (
            OSError,
            RuntimeError,
            S3StoreError,
        ) as error:
            failed += 1

            print(
                f"[{index}/{len(json_objects)}] "
                f"FAILED {obj.key}: {error}",
                file=sys.stderr,
            )

    return downloaded, failed


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Download every JSON sidecar from the S3 verified/ namespace."
        )
    )

    parser.add_argument(
        "output_folder",
        type=Path,
        help="Local folder where verified JSON sidecars will be downloaded",
    )

    parser.add_argument(
        "--profile",
        default=DEFAULT_PROFILE,
        help=(
            "AWS credential profile name "
            f"(default: {DEFAULT_PROFILE})"
        ),
    )

    arguments = parser.parse_args()

    try:
        downloaded, failed = download_verified_sidecars(
            arguments.output_folder,
            profile_name=arguments.profile,
        )

    except (
        AwsAuthError,
        OSError,
        RuntimeError,
        S3StoreError,
        ValueError,
    ) as error:
        print(
            f"Download failed: {error}",
            file=sys.stderr,
        )
        return 1

    print()
    print(f"Downloaded: {downloaded}")
    print(f"Failed: {failed}")

    return 0 if failed == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
