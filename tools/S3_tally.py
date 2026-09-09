"""
Print Pi Camera Capture inventory counts from S3 object keys.

Counts capture pairs by counting only .mp4 objects. No sidecars or videos are
downloaded.

Expected canonical key layouts:

    verified/<classification>/<type>/...
    unverified/<H-M-L classification>/...

Default AWS profile is picam-manager because inventory requires bucket-list
permission. The bucket name is read from ~/.picam/aws_credentials.json.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import json
import sys

from common.aws_auth import AwsAuthConfig, AwsAuthenticator
from common.s3_store import S3Store


def build_store(
    profile_name: str,
    bucket_override: str | None = None,
) -> S3Store:
    authenticator = AwsAuthenticator(
        AwsAuthConfig(
            profile_name=profile_name,
        )
    )

    bucket_name = str(
        bucket_override or ""
    ).strip()

    if not bucket_name:
        try:
            document = json.loads(
                authenticator.credential_file.read_text(
                    encoding="utf-8",
                )
            )
        except (
            OSError,
            json.JSONDecodeError,
        ) as error:
            raise RuntimeError(
                f"Unable to read AWS bucket configuration: {error}"
            ) from error

        bucket_name = str(
            document.get(
                "bucket",
                "",
            ) or ""
        ).strip()

    if not bucket_name:
        raise RuntimeError(
            "AWS bucket name is missing"
        )

    return S3Store(
        bucket_name,
        authenticator,
    )


def count_capture_keys(
    store: S3Store,
) -> tuple[
    dict[str, Counter[str]],
    Counter[str],
    Counter[str],
]:
    verified: dict[
        str,
        Counter[str],
    ] = defaultdict(
        Counter
    )

    unverified: Counter[str] = (
        Counter()
    )

    other: Counter[str] = (
        Counter()
    )

    for item in store.list_objects():
        key = item.key

        if not key.lower().endswith(
            ".mp4"
        ):
            continue

        parts = key.split(
            "/"
        )

        if (
            len(parts) >= 4
            and parts[0] == "verified"
        ):
            classification = (
                parts[1] or "<blank>"
            )

            lightning_type = (
                parts[2] or "<blank>"
            )

            verified[
                classification
            ][
                lightning_type
            ] += 1

        elif (
            len(parts) >= 3
            and parts[0] == "unverified"
        ):
            classification = (
                parts[1] or "<blank>"
            )

            unverified[
                classification
            ] += 1

        else:
            root = (
                parts[0]
                if parts
                else "<blank>"
            )

            other[
                root or "<blank>"
            ] += 1

    return (
        dict(
            verified
        ),
        unverified,
        other,
    )


def print_inventory(
    bucket_name: str,
    verified: dict[str, Counter[str]],
    unverified: Counter[str],
    other: Counter[str],
) -> None:
    print()
    print(
        f"S3 Capture Inventory: {bucket_name}"
    )
    print(
        "=" * (
            len(
                "S3 Capture Inventory: "
            )
            + len(
                bucket_name
            )
        )
    )

    verified_total = 0

    print()
    print("Verified")
    print("--------")

    if not verified:
        print("  (none)")
    else:
        for classification in sorted(
            verified
        ):
            type_counts = verified[
                classification
            ]

            classification_total = sum(
                type_counts.values()
            )

            verified_total += (
                classification_total
            )

            print(
                f"  {classification}"
            )

            for lightning_type in sorted(
                type_counts
            ):
                print(
                    f"    "
                    f"{lightning_type:<8}"
                    f"{type_counts[lightning_type]:>8}"
                )

            print(
                f"    "
                f"{'TOTAL':<8}"
                f"{classification_total:>8}"
            )

    unverified_total = sum(
        unverified.values()
    )

    print()
    print("Unverified")
    print("----------")

    if not unverified:
        print("  (none)")
    else:
        for classification in sorted(
            unverified
        ):
            print(
                f"  "
                f"{classification:<20}"
                f"{unverified[classification]:>8}"
            )

        print(
            f"  "
            f"{'TOTAL':<20}"
            f"{unverified_total:>8}"
        )

    other_total = sum(
        other.values()
    )

    if other_total:
        print()
        print("Other MP4 objects")
        print("-----------------")

        for root in sorted(
            other
        ):
            print(
                f"  "
                f"{root:<20}"
                f"{other[root]:>8}"
            )

        print(
            f"  "
            f"{'TOTAL':<20}"
            f"{other_total:>8}"
        )

    print()
    print(
        f"TOTAL CAPTURES: "
        f"{verified_total + unverified_total + other_total}"
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Count Pi Camera Capture objects in S3 "
            "by classification and lightning type."
        )
    )

    parser.add_argument(
        "--profile",
        default="picam-manager",
        help=(
            "AWS credential profile from ~/.picam/aws_credentials.json "
            "(default: picam-manager)"
        ),
    )

    parser.add_argument(
        "--bucket",
        default=None,
        help=(
            "Optional S3 bucket override. "
            "Default: bucket from ~/.picam/aws_credentials.json"
        ),
    )

    args = parser.parse_args()

    try:
        store = build_store(
            profile_name=args.profile,
            bucket_override=args.bucket,
        )

        (
            verified,
            unverified,
            other,
        ) = count_capture_keys(
            store
        )

        print_inventory(
            store.bucket_name,
            verified,
            unverified,
            other,
        )

    except Exception as error:
        print(
            f"S3 inventory failed: {error}",
            file=sys.stderr,
        )
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(
        main()
    )
