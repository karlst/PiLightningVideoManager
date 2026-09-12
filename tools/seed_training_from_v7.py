r"""
@file seed_training_from_v7.py

@brief One-time tool to seed the S3 training collection from historical V7 labels.

The tool reads historical V7 JSON sidecars, finds each matching migrated V8 JSON
sidecar, groups the matched V8 sidecars by the original V7 classification, and
selects at most --cap items from each classification using a reproducible random
sample.

Only V8 JSON sidecars are uploaded. MP4 files are never uploaded.

Training object keys are:

    training/<V7-classification>/<site>/<V8-stem>.json

Examples:

    # Validate matching and show the exact sample without writing S3.
    python -m tools.seed_training_from_v7 E:\V7Sidecars E:\V8Sidecars --dry-run

    # Seed S3 with at most 250 captures per V7 classification.
    python -m tools.seed_training_from_v7 E:\V7Sidecars E:\V8Sidecars

    # Use a different cap or deterministic random seed.
    python -m tools.seed_training_from_v7 E:\V7Sidecars E:\V8Sidecars --cap 200 --seed 1234

The V7 classification is used only as the training collection label. The JSON
stored in S3 is the corresponding current V8 sidecar.

Matching is based on preserved capture timestamps, primarily capture.saved_utc,
with capture.start_utc and candidate.trigger_utc used as additional/fallback
identifiers. Ambiguous or unmatched captures are reported and never guessed.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import random
import sys
from typing import Any

from common.aws_auth import AwsAuthConfig, AwsAuthenticator
from common.s3_store import S3Store, S3StoreError


DEFAULT_BUCKET = "soloran-picam"
DEFAULT_PROFILE = "picam-manager"
DEFAULT_CAP = 250
DEFAULT_SEED = 3709

V7_LABELS = (
    "TF",
    "NA",
    "NAC",
    "SSA",
    "STA",
    "FDA",
    "UFA",
)


@dataclass(frozen=True)
class SidecarRecord:
    path: Path
    document: dict[str, Any]
    saved_utc: str | None
    start_utc: str | None
    trigger_utc: str | None


@dataclass(frozen=True)
class MatchedRecord:
    label: str
    v7: SidecarRecord
    v8: SidecarRecord


def _read_json(path: Path) -> dict[str, Any]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except OSError as error:
        raise RuntimeError(f"Unable to read {path}: {error}") from error
    except json.JSONDecodeError as error:
        raise RuntimeError(f"Invalid JSON {path}: {error}") from error

    if not isinstance(document, dict):
        raise RuntimeError(f"Sidecar root is not a JSON object: {path}")

    return document


def _normalized_utc(value: Any) -> str | None:
    """Normalize a UTC timestamp to an exact microsecond-resolution key."""
    if not isinstance(value, str) or not value.strip():
        return None

    text = value.strip()

    try:
        if text.endswith("Z"):
            dt = datetime.fromisoformat(text[:-1] + "+00:00")
        else:
            dt = datetime.fromisoformat(text)
    except ValueError:
        return None

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)

    return dt.isoformat(timespec="microseconds")


def _capture_timestamp(
    document: dict[str, Any],
    name: str,
) -> str | None:
    capture = document.get("capture")
    if not isinstance(capture, dict):
        return None
    return _normalized_utc(capture.get(name))


def _trigger_timestamp(
    document: dict[str, Any],
) -> str | None:
    candidate = document.get("candidate")
    if not isinstance(candidate, dict):
        return None
    return _normalized_utc(candidate.get("trigger_utc"))


def _load_record(path: Path, expected_version: int) -> SidecarRecord:
    document = _read_json(path)

    version = document.get("sidecar_version")
    if version != expected_version:
        raise RuntimeError(
            f"{path}: sidecar_version={version!r}; expected {expected_version}"
        )

    return SidecarRecord(
        path=path,
        document=document,
        saved_utc=_capture_timestamp(document, "saved_utc"),
        start_utc=_capture_timestamp(document, "start_utc"),
        trigger_utc=_trigger_timestamp(document),
    )


def _collect_records(
    folder: Path,
    expected_version: int,
) -> tuple[list[SidecarRecord], list[str]]:
    records: list[SidecarRecord] = []
    problems: list[str] = []

    for path in sorted(folder.rglob("*.json")):
        try:
            records.append(_load_record(path, expected_version))
        except RuntimeError as error:
            problems.append(str(error))

    return records, problems


def _v7_label(record: SidecarRecord) -> str | None:
    capture = record.document.get("capture")
    if not isinstance(capture, dict):
        return None

    label = str(capture.get("classification", "") or "").strip().upper()
    return label if label in V7_LABELS else None


def _make_index(
    records: list[SidecarRecord],
    field_name: str,
) -> dict[str, list[SidecarRecord]]:
    index: dict[str, list[SidecarRecord]] = defaultdict(list)

    for record in records:
        value = getattr(record, field_name)
        if value:
            index[value].append(record)

    return dict(index)


def _unique_candidate(
    index: dict[str, list[SidecarRecord]],
    value: str | None,
) -> SidecarRecord | None:
    if not value:
        return None

    candidates = index.get(value, [])
    return candidates[0] if len(candidates) == 1 else None


def _match_v8(
    v7: SidecarRecord,
    saved_index: dict[str, list[SidecarRecord]],
    start_index: dict[str, list[SidecarRecord]],
    trigger_index: dict[str, list[SidecarRecord]],
) -> tuple[SidecarRecord | None, str | None]:
    """Return one unambiguous V8 match, or an explanatory failure reason."""

    # Primary match: capture.saved_utc.
    if v7.saved_utc:
        candidates = saved_index.get(v7.saved_utc, [])
        if len(candidates) == 1:
            return candidates[0], None
        if len(candidates) > 1:
            narrowed = [
                item
                for item in candidates
                if (
                    (not v7.start_utc or item.start_utc == v7.start_utc)
                    and (
                        not v7.trigger_utc
                        or item.trigger_utc == v7.trigger_utc
                    )
                )
            ]
            if len(narrowed) == 1:
                return narrowed[0], None
            return None, (
                f"ambiguous saved_utc match ({len(candidates)} V8 candidates)"
            )

    # Fallback: capture.start_utc.
    match = _unique_candidate(start_index, v7.start_utc)
    if match is not None:
        return match, None

    # Final fallback: candidate.trigger_utc.
    match = _unique_candidate(trigger_index, v7.trigger_utc)
    if match is not None:
        return match, None

    return None, "no matching V8 sidecar"


def _site_name(v8: SidecarRecord) -> str:
    camera = v8.document.get("camera")
    site = ""

    if isinstance(camera, dict):
        site = str(camera.get("site_name", "") or "").strip()

    return _safe_segment(site or "Unknown")


def _safe_segment(value: str) -> str:
    return value.strip().replace("/", "_").replace("\\", "_") or "Unknown"


def _training_key(label: str, v8: SidecarRecord) -> str:
    site = _site_name(v8)
    stem = v8.path.stem
    return f"training/{label}/{site}/{stem}.json"


def _sample_by_label(
    matched: list[MatchedRecord],
    cap: int,
    seed: int,
) -> dict[str, list[MatchedRecord]]:
    grouped: dict[str, list[MatchedRecord]] = defaultdict(list)

    for item in matched:
        grouped[item.label].append(item)

    selected: dict[str, list[MatchedRecord]] = {}
    rng = random.Random(seed)

    # Sample each class independently in a stable class order.
    for label in V7_LABELS:
        items = sorted(
            grouped.get(label, []),
            key=lambda item: str(item.v7.path).lower(),
        )

        if len(items) <= cap:
            chosen = items
        else:
            chosen = rng.sample(items, cap)
            chosen.sort(key=lambda item: str(item.v7.path).lower())

        selected[label] = chosen

    return selected


def _print_count_table(
    title: str,
    counts: Counter[str],
) -> None:
    print()
    print(title)
    for label in V7_LABELS:
        print(f"  {label:<4} {counts.get(label, 0):6d}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Seed S3 training JSONs from V7 classifications and matching "
            "migrated V8 sidecars."
        )
    )

    parser.add_argument(
        "v7_folder",
        type=Path,
        help="Folder containing historical V7 JSON sidecars",
    )
    parser.add_argument(
        "v8_folder",
        type=Path,
        help="Folder containing migrated V8 JSON sidecars",
    )
    parser.add_argument(
        "--cap",
        type=int,
        default=DEFAULT_CAP,
        help=f"Maximum selected per V7 classification; default: {DEFAULT_CAP}",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=DEFAULT_SEED,
        help=f"Deterministic random-sampling seed; default: {DEFAULT_SEED}",
    )
    parser.add_argument(
        "--bucket",
        default=DEFAULT_BUCKET,
        help=f"S3 bucket; default: {DEFAULT_BUCKET}",
    )
    parser.add_argument(
        "--profile",
        default=DEFAULT_PROFILE,
        help=f"AWS credential profile; default: {DEFAULT_PROFILE}",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show matching, sampling, and keys without uploading",
    )
    parser.add_argument(
        "--overwrite-existing",
        action="store_true",
        help="Overwrite training JSONs already present in S3",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Print each selected/uploaded training object",
    )

    args = parser.parse_args()

    v7_folder = args.v7_folder.expanduser()
    v8_folder = args.v8_folder.expanduser()

    if not v7_folder.is_dir():
        parser.error(f"V7 folder not found: {v7_folder}")
    if not v8_folder.is_dir():
        parser.error(f"V8 folder not found: {v8_folder}")
    if args.cap < 1:
        parser.error("--cap must be at least 1")

    print(f"V7 folder: {v7_folder}")
    print(f"V8 folder: {v8_folder}")
    print(f"Per-class cap: {args.cap}")
    print(f"Random seed: {args.seed}")

    v7_records, v7_load_problems = _collect_records(v7_folder, 7)
    v8_records, v8_load_problems = _collect_records(v8_folder, 8)

    print(f"V7 sidecars loaded: {len(v7_records)}")
    print(f"V8 sidecars loaded: {len(v8_records)}")

    saved_index = _make_index(v8_records, "saved_utc")
    start_index = _make_index(v8_records, "start_utc")
    trigger_index = _make_index(v8_records, "trigger_utc")

    source_counts: Counter[str] = Counter()
    matched_counts: Counter[str] = Counter()
    unsupported_count = 0
    unmatched: list[tuple[Path, str, str]] = []
    matched: list[MatchedRecord] = []

    for v7 in v7_records:
        label = _v7_label(v7)

        if label is None:
            unsupported_count += 1
            continue

        source_counts[label] += 1

        v8, reason = _match_v8(
            v7,
            saved_index,
            start_index,
            trigger_index,
        )

        if v8 is None:
            unmatched.append((v7.path, label, reason or "unmatched"))
            continue

        matched.append(MatchedRecord(label=label, v7=v7, v8=v8))
        matched_counts[label] += 1

    selected = _sample_by_label(matched, args.cap, args.seed)
    selected_counts = Counter(
        {
            label: len(items)
            for label, items in selected.items()
        }
    )

    _print_count_table("V7 classifications:", source_counts)
    _print_count_table("Matched to V8:", matched_counts)
    _print_count_table("Selected for training:", selected_counts)

    print()
    print(f"Unsupported/unclassified V7 sidecars: {unsupported_count}")
    print(f"Unmatched V7 sidecars: {len(unmatched)}")
    print(f"Invalid V7 JSON/version: {len(v7_load_problems)}")
    print(f"Invalid V8 JSON/version: {len(v8_load_problems)}")
    print(f"Total selected: {sum(selected_counts.values())}")

    if unmatched:
        print()
        print("Unmatched:")
        for path, label, reason in unmatched:
            print(f"  {label:<4} {path}: {reason}")

    if v7_load_problems:
        print()
        print("V7 load problems:")
        for problem in v7_load_problems:
            print(f"  {problem}")

    if v8_load_problems:
        print()
        print("V8 load problems:")
        for problem in v8_load_problems:
            print(f"  {problem}")

    if args.dry_run:
        print()
        print("DRY RUN - no S3 objects written")

        for label in V7_LABELS:
            for item in selected[label]:
                print(f"  {_training_key(label, item.v8)}")

        return 0

    try:
        authenticator = AwsAuthenticator(
            AwsAuthConfig(profile_name=args.profile)
        )
        store = S3Store(args.bucket, authenticator)
        existing_training_keys = {
            item.key
            for item in store.list_objects(prefix="training/")
        }
    except Exception as error:
        print(f"Unable to initialize/list S3: {error}")
        return 1

    uploaded_counts: Counter[str] = Counter()
    skipped_counts: Counter[str] = Counter()
    failed_counts: Counter[str] = Counter()

    for label in V7_LABELS:
        for item in selected[label]:
            key = _training_key(label, item.v8)

            if key in existing_training_keys and not args.overwrite_existing:
                skipped_counts[label] += 1
                if args.verbose:
                    print(f"SKIP   {key}")
                continue

            try:
                store.upload_file(item.v8.path, key)
                uploaded_counts[label] += 1
                existing_training_keys.add(key)

                if args.verbose:
                    print(f"UPLOAD {key}")

            except (OSError, S3StoreError, RuntimeError) as error:
                failed_counts[label] += 1
                print(f"FAIL   {key}: {error}")

    _print_count_table("Uploaded:", uploaded_counts)
    _print_count_table("Skipped existing:", skipped_counts)
    _print_count_table("Failed:", failed_counts)

    print()
    print(f"Uploaded total: {sum(uploaded_counts.values())}")
    print(f"Skipped total: {sum(skipped_counts.values())}")
    print(f"Failed total: {sum(failed_counts.values())}")

    return 0 if not failed_counts else 1


if __name__ == "__main__":
    sys.exit(main())
