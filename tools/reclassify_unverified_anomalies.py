"""
One-off batch repair for unverified V7 captures.

For every unverified capture_*.mp4 with a matching V7 JSON sidecar:
- Run the current SolutionFilter using sidecar brightness metrics and the
  recorded Candidate trigger. The MP4 is not decoded.
- If SolutionFilter returns a recognized anomaly, mark the sidecar verified
  and store the final anomaly classification with type UK.
- If SolutionFilter returns TRUE_FLASH, leave the sidecar unchanged.
- Already-verified captures are skipped.
- No MP4 files are moved, renamed, or deleted.

Examples:
    python tools/reclassify_unverified_anomalies.py C:\\capturesV7 --dry-run
    python tools/reclassify_unverified_anomalies.py C:\\capturesV7
    python tools/reclassify_unverified_anomalies.py C:\\Lightning --recursive
"""

from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import sys
from typing import Any

from common.candidate_config import CANDIDATE_CONFIG
from common.capture_sidecar import SIDECAR_VERSION, normalize_sidecar
from common.solution_batch import ANOMALY_CLASSIFICATION_CODES, classify_capture
from video_analyzer.solution_config import solution_config_for_sensitivity
from video_analyzer.solution_filter import SolutionFilter
from video_analyzer.solution_types import CATEGORY_TRUE_FLASH


def read_sidecar(sidecar_path: Path) -> dict[str, Any]:
    try:
        data = json.loads(sidecar_path.read_text(encoding="utf-8-sig"))
    except OSError as error:
        raise RuntimeError(f"Unable to read sidecar: {error}") from error
    except json.JSONDecodeError as error:
        raise RuntimeError(f"Invalid JSON: {error}") from error

    if not isinstance(data, dict):
        raise RuntimeError("Sidecar root must be a JSON object")

    normalized, _changed = normalize_sidecar(data)

    if normalized.get("sidecar_version") != SIDECAR_VERSION:
        raise RuntimeError(f"Expected sidecar version {SIDECAR_VERSION}")

    return normalized


def write_sidecar_atomic(sidecar_path: Path, sidecar: dict[str, Any]) -> None:
    temporary_path = sidecar_path.with_suffix(".json.tmp")

    temporary_path.write_text(
        json.dumps(sidecar, indent=4) + "\n",
        encoding="utf-8",
    )

    try:
        staged = json.loads(temporary_path.read_text(encoding="utf-8"))
    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise

    if not isinstance(staged, dict):
        temporary_path.unlink(missing_ok=True)
        raise RuntimeError("Temporary sidecar root is not a JSON object")

    temporary_path.replace(sidecar_path)


def collect_video_files(folder: Path, recursive: bool) -> list[Path]:
    pattern = "**/capture_*.mp4" if recursive else "capture_*.mp4"
    return sorted(folder.glob(pattern))


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "One-off pass: run current SolutionFilter on unverified V7 "
            "captures and automatically verify recognized anomalies."
        )
    )

    parser.add_argument(
        "folder",
        type=Path,
        help="Folder containing capture_*.mp4 files and matching JSON sidecars",
    )
    parser.add_argument(
        "--recursive",
        action="store_true",
        help="Process capture_*.mp4 files in subfolders recursively",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show which sidecars would be updated without changing files",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Print TRUE_FLASH and already-verified skips as well as updates",
    )

    arguments = parser.parse_args()
    folder = arguments.folder.expanduser()

    if not folder.is_dir():
        print(f"Folder not found: {folder}")
        return 1

    video_files = collect_video_files(folder, arguments.recursive)

    solution_filter = SolutionFilter(
        solution_config_for_sensitivity(CANDIDATE_CONFIG.sensitivity)
    )

    counts: Counter[str] = Counter()

    for video_path in video_files:
        sidecar_path = video_path.with_suffix(".json")

        if not sidecar_path.is_file():
            print(f"FAIL  {video_path}: matching JSON sidecar not found")
            counts["failed"] += 1
            continue

        try:
            sidecar = read_sidecar(sidecar_path)
            capture = sidecar.get("capture")

            if not isinstance(capture, dict):
                raise RuntimeError("Missing capture object")

            if capture.get("verified") is True:
                counts["already_verified"] += 1
                if arguments.verbose:
                    print(f"SKIP  {video_path.name}: already verified")
                continue

            category, reason = classify_capture(
                video_path,
                solution_filter,
                candidate_config=CANDIDATE_CONFIG,
                find_candidates=False,
                verbosity=0,
            )

            classification = ANOMALY_CLASSIFICATION_CODES.get(category)

            if classification is None:
                if category == CATEGORY_TRUE_FLASH:
                    counts["true_flash"] += 1
                    if arguments.verbose:
                        print(f"KEEP  {video_path.name}: TRUE_FLASH — {reason}")
                else:
                    counts["unclassified"] += 1
                    print(f"SKIP  {video_path.name}: {category} — {reason}")
                continue

            old_classification = str(capture.get("classification", "") or "")
            capture["verified"] = True
            capture["classification"] = classification
            capture["type"] = "UK"

            if arguments.dry_run:
                print(
                    f"WOULD UPDATE  {video_path.name}: "
                    f"{old_classification} -> {classification}  "
                    f"verified=True  ({reason})"
                )
            else:
                write_sidecar_atomic(sidecar_path, sidecar)
                print(
                    f"UPDATED  {video_path.name}: "
                    f"{old_classification} -> {classification}  "
                    f"verified=True  ({reason})"
                )

            counts[classification] += 1
            counts["updated"] += 1

        except Exception as error:
            counts["failed"] += 1
            print(f"FAIL  {video_path.name}: {error}")

    print()
    print("Dry run summary:" if arguments.dry_run else "Summary:")
    print(f"  capture_ files found: {len(video_files)}")
    print(f"  Already verified:     {counts['already_verified']}")
    print(f"  True flash unchanged: {counts['true_flash']}")
    print(f"  Anomalies updated:    {counts['updated']}")
    print(f"    NA:                 {counts['NA']}")
    print(f"    SSA:                {counts['SSA']}")
    print(f"    STA:                {counts['STA']}")
    print(f"    FDA:                {counts['FDA']}")
    print(f"  Unclassified/skipped: {counts['unclassified']}")
    print(f"  Failed:               {counts['failed']}")

    return 0 if counts["failed"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
