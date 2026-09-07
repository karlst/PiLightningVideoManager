"""
@file batch_upload_captures.py

@brief Upload a folder of migrated V7 Pi Camera captures to S3.

Each capture is an MP4 plus matching JSON sidecar. S3 object keys are derived
from current V7 sidecar metadata using common.capture_key.

Behavior:
* Uses AWS profile "picam-manager" by default.
* Local files are never deleted or modified.
* If both S3 pair objects already exist, the capture is skipped by default.
  With --overwrite-existing, both objects are uploaded again.
* If only one S3 pair object exists, both objects are uploaded, overwriting the
  partial pair and restoring a complete consistent pair.
* If neither exists, both objects are uploaded.
* Uploads run concurrently across captures. The default is 8 workers.
* Small MP4/JSON files use direct PutObject uploads rather than boto3's transfer
  manager.
* A failed upload never deletes an existing S3 object.

Examples:

    python tools/batch_upload_captures.py C:\\S3Staging
    python tools/batch_upload_captures.py C:\\S3Staging --bucket soloran-picam
    python tools/batch_upload_captures.py C:\\S3Staging --workers 8
    python tools/batch_upload_captures.py C:\\S3Staging --overwrite-existing
    python tools/batch_upload_captures.py C:\\S3Staging --dry-run
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
from pathlib import Path
import sys
import time
from typing import Any

from common.aws_auth import (
    AwsAuthConfig,
    AwsAuthenticator,
)
from common.capture_key import (
    canonical_capture_base_key,
    pair_keys,
)
from common.capture_sidecar import normalize_sidecar
from common.s3_store import S3Store


DEFAULT_PROFILE = "picam-manager"
DEFAULT_BUCKET = "soloran-picam"


def read_sidecar(
    sidecar_path: Path,
) -> dict[str, Any]:
    try:
        data = json.loads(
            sidecar_path.read_text(
                encoding="utf-8-sig"
            )
        )
    except OSError as error:
        raise RuntimeError(
            f"Unable to read sidecar: {error}"
        ) from error
    except json.JSONDecodeError as error:
        raise RuntimeError(
            f"Invalid sidecar JSON: {error}"
        ) from error

    if not isinstance(
        data,
        dict,
    ):
        raise RuntimeError(
            "Sidecar JSON root must be an object"
        )

    normalized, _changed = normalize_sidecar(
        data
    )

    return normalized


def collect_capture_pairs(
    folder: Path,
) -> list[tuple[Path, Path]]:
    pairs: list[tuple[Path, Path]] = []

    for video_path in sorted(
        folder.glob(
            "*.mp4"
        )
    ):
        sidecar_path = video_path.with_suffix(
            ".json"
        )

        pairs.append(
            (
                video_path,
                sidecar_path,
            )
        )

    return pairs


def existing_capture_keys(
    store: S3Store,
) -> set[str]:
    keys: set[str] = set()

    for prefix in (
        "unverified/",
        "verified/",
    ):
        for obj in store.list_objects(
            prefix
        ):
            keys.add(
                obj.key
            )

    return keys



def upload_capture_pair(
    store: S3Store,
    video_path: Path,
    sidecar_path: Path,
    mp4_key: str,
    json_key: str,
) -> float:
    """Upload one MP4/JSON pair and return elapsed seconds.

    These capture objects are small, so direct PutObject calls avoid the
    transfer-manager overhead of upload_file().
    """
    start = time.perf_counter()

    video_bytes = video_path.read_bytes()
    sidecar_bytes = sidecar_path.read_bytes()

    store.upload_bytes(
        video_bytes,
        mp4_key,
        content_type="video/mp4",
    )

    store.upload_bytes(
        sidecar_bytes,
        json_key,
        content_type="application/json",
    )

    return (
        time.perf_counter()
        - start
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Upload migrated V7 Pi Camera MP4/JSON capture pairs to S3."
        )
    )

    parser.add_argument(
        "folder",
        type=Path,
        help=(
            "Flat folder containing migrated MP4/JSON capture pairs"
        ),
    )

    parser.add_argument(
        "--bucket",
        default=DEFAULT_BUCKET,
        help=(
            f"S3 bucket name; default: {DEFAULT_BUCKET}"
        ),
    )

    parser.add_argument(
        "--profile",
        default=DEFAULT_PROFILE,
        help=(
            f"AWS credential profile; default: {DEFAULT_PROFILE}"
        ),
    )

    parser.add_argument(
        "--workers",
        type=int,
        default=8,
        help=(
            "Number of captures uploaded concurrently; default: 8"
        ),
    )

    parser.add_argument(
        "--overwrite-existing",
        action="store_true",
        help=(
            "Overwrite complete capture pairs that already exist in S3. "
            "Default is to skip complete duplicates. Partial pairs are always "
            "repaired by uploading both objects."
        ),
    )

    parser.add_argument(
        "--progress-interval",
        type=float,
        default=1.0,
        help=(
            "Seconds between console progress updates; default: 1.0. "
            "Set to 0 to disable progress output."
        ),
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "Validate sidecars and show intended S3 keys without uploading"
        ),
    )

    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help=(
            "Print one line for every successfully uploaded capture"
        ),
    )

    arguments = parser.parse_args()

    folder = arguments.folder.expanduser()

    if not folder.is_dir():
        print(
            f"Folder not found: {folder}"
        )
        return 1

    if arguments.workers < 1:
        parser.error(
            "--workers must be at least 1"
        )

    if arguments.progress_interval < 0:
        parser.error(
            "--progress-interval must be 0 or greater"
        )

    pairs = collect_capture_pairs(
        folder
    )

    authenticator = AwsAuthenticator(
        AwsAuthConfig(
            profile_name=arguments.profile
        )
    )

    try:
        store = S3Store(
            arguments.bucket,
            authenticator,
        )

        # One bucket listing is much cheaper than two HEAD requests per capture.
        existing_keys = (
            set()
            if arguments.dry_run
            else existing_capture_keys(
                store
            )
        )

    except Exception as error:
        print(
            f"Unable to initialize S3: {error}"
        )
        return 1

    start_time = time.perf_counter()

    uploaded_count = 0
    duplicate_count = 0
    overwritten_count = 0
    partial_overwrite_count = 0
    failed_count = 0
    missing_sidecar_count = 0

    completed_count = 0
    last_progress_time = start_time

    upload_jobs: list[
        tuple[
            Path,
            Path,
            str,
            str,
            str,
            bool,
            bool,
        ]
    ] = []

    # Validate metadata and determine upload policy before starting workers.
    for video_path, sidecar_path in pairs:
        if not sidecar_path.is_file():
            missing_sidecar_count += 1
            failed_count += 1
            completed_count += 1

            print(
                f"FAIL  {video_path.name}: "
                "matching JSON sidecar not found"
            )
            continue

        try:
            sidecar = read_sidecar(
                sidecar_path
            )

            base_key = canonical_capture_base_key(
                sidecar,
                fallback_stem=video_path.stem,
            )

            mp4_key, json_key = pair_keys(
                base_key
            )

            mp4_exists = (
                mp4_key in existing_keys
            )
            json_exists = (
                json_key in existing_keys
            )

            complete_pair = (
                mp4_exists
                and json_exists
            )

            partial_pair = (
                mp4_exists
                != json_exists
            )

            if (
                complete_pair
                and not arguments.overwrite_existing
            ):
                duplicate_count += 1
                completed_count += 1

                if arguments.verbose:
                    print(
                        f"SKIP DUPLICATE  {video_path.name}  "
                        f"-> {base_key}"
                    )

                continue

            if arguments.dry_run:
                if partial_pair:
                    action = "WOULD OVERWRITE PARTIAL"
                    partial_overwrite_count += 1
                elif complete_pair:
                    action = "WOULD OVERWRITE"
                    overwritten_count += 1
                else:
                    action = "WOULD UPLOAD"

                print(
                    f"{action}  {video_path.name}  "
                    f"-> {base_key}"
                )

                uploaded_count += 1
                completed_count += 1
                continue

            upload_jobs.append(
                (
                    video_path,
                    sidecar_path,
                    mp4_key,
                    json_key,
                    base_key,
                    complete_pair,
                    partial_pair,
                )
            )

        except Exception as error:
            failed_count += 1
            completed_count += 1

            print(
                f"FAIL  {video_path.name}: {error}"
            )

    def show_progress(
        force: bool = False,
    ) -> None:
        nonlocal last_progress_time

        if arguments.progress_interval <= 0:
            return

        now = time.perf_counter()

        if (
            not force
            and now - last_progress_time
            < arguments.progress_interval
        ):
            return

        elapsed = now - start_time

        rate = (
            completed_count / elapsed
            if elapsed > 0
            else 0.0
        )

        remaining = (
            len(pairs) - completed_count
        )

        eta = (
            remaining / rate
            if rate > 0
            else 0.0
        )

        print(
            f"\rProgress: {completed_count}/{len(pairs)}  "
            f"uploaded={uploaded_count}  "
            f"skipped={duplicate_count}  "
            f"failed={failed_count}  "
            f"rate={rate:.2f} captures/s  "
            f"ETA={eta:.0f}s",
            end="",
            flush=True,
        )

        last_progress_time = now

    if (
        not arguments.dry_run
        and upload_jobs
    ):
        with ThreadPoolExecutor(
            max_workers=arguments.workers
        ) as executor:
            future_to_job = {
                executor.submit(
                    upload_capture_pair,
                    store,
                    video_path,
                    sidecar_path,
                    mp4_key,
                    json_key,
                ): (
                    video_path,
                    mp4_key,
                    json_key,
                    base_key,
                    complete_pair,
                    partial_pair,
                )
                for (
                    video_path,
                    sidecar_path,
                    mp4_key,
                    json_key,
                    base_key,
                    complete_pair,
                    partial_pair,
                ) in upload_jobs
            }

            for future in as_completed(
                future_to_job
            ):
                (
                    video_path,
                    mp4_key,
                    json_key,
                    base_key,
                    complete_pair,
                    partial_pair,
                ) = future_to_job[
                    future
                ]

                try:
                    capture_elapsed = future.result()

                    uploaded_count += 1
                    completed_count += 1

                    if partial_pair:
                        partial_overwrite_count += 1
                    elif complete_pair:
                        overwritten_count += 1

                    # Keep the local key set consistent for diagnostics and
                    # possible future extensions. Jobs were deduplicated by the
                    # initial S3 listing before workers started.
                    existing_keys.add(
                        mp4_key
                    )
                    existing_keys.add(
                        json_key
                    )

                    if arguments.verbose:
                        if partial_pair:
                            action = "OVERWROTE PARTIAL"
                        elif complete_pair:
                            action = "OVERWROTE"
                        else:
                            action = "UPLOADED"

                        print(
                            f"{action}  {video_path.name}  "
                            f"{capture_elapsed:.3f}s  -> {base_key}"
                        )

                    show_progress()

                except Exception as error:
                    failed_count += 1
                    completed_count += 1

                    print(
                        f"FAIL  {video_path.name}: {error}"
                    )

                    show_progress()

    if not arguments.dry_run:
        show_progress(
            force=True
        )

        if (
            arguments.progress_interval > 0
            and pairs
        ):
            print()

    elapsed_total = (
        time.perf_counter()
        - start_time
    )

    average_time = (
        elapsed_total / uploaded_count
        if uploaded_count
        else 0.0
    )

    print()
    print(
        "Dry run summary:"
        if arguments.dry_run
        else "Upload summary:"
    )
    print(
        f"  Captures found:       {len(pairs)}"
    )
    print(
        f"  Captures uploaded:    {uploaded_count}"
    )
    print(
        f"  Duplicate skips:      {duplicate_count}"
    )
    print(
        f"  Complete overwrites:  {overwritten_count}"
    )
    print(
        f"  Partial overwrites:   {partial_overwrite_count}"
    )
    print(
        f"  Missing sidecars:     {missing_sidecar_count}"
    )
    print(
        f"  Failed:               {failed_count}"
    )
    print(
        f"  Total time:           {elapsed_total:.3f} s"
    )
    print(
        f"  Average per upload:   {average_time:.3f} s"
    )

    return (
        0
        if failed_count == 0
        else 1
    )


if __name__ == "__main__":
    sys.exit(
        main()
    )
