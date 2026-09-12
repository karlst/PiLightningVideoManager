"""
@file summarize_captures.py

@brief Summarize classifications and lightning types in a folder of captures.

The tool examines MP4 files and their matching JSON sidecars. By default it
expects current V8 sidecars. Use --sidecar-version 7 to summarize a historical
V7 capture folder, including legacy classifications such as FDA, SSA, STA, NA,
NAC, UFA and TF.

Both V7 and V8 store the workflow metadata used by this tool under "capture":

    capture.verified
    capture.classification
    capture.type

The requested sidecar version is checked exactly. The tool does not modify any
files.

Examples:

    python -m tools.summarize_captures C:\\S3Staging
    python -m tools.summarize_captures C:\\Lightning --recursive
    python -m tools.summarize_captures E:\\SideCarsFromS3\\training --recursive --sidecar-version 7
"""

from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import sys
from typing import Any

from common.capture_sidecar import SIDECAR_VERSION


SUPPORTED_SIDECAR_VERSIONS = (7, 8)


def read_sidecar(sidecar_path: Path) -> dict[str, Any]:
    try:
        data = json.loads(sidecar_path.read_text(encoding="utf-8"))
    except OSError as error:
        raise RuntimeError(f"Unable to read sidecar: {error}") from error
    except json.JSONDecodeError as error:
        raise RuntimeError(f"Invalid JSON: {error}") from error

    if not isinstance(data, dict):
        raise RuntimeError("Sidecar root is not a JSON object")

    return data


def capture_metadata(
    sidecar: dict[str, Any],
    expected_sidecar_version: int,
) -> tuple[bool, str, str, float, float]:
    version = sidecar.get("sidecar_version")

    if version != expected_sidecar_version:
        raise RuntimeError(
            f"sidecar_version={version!r}; expected {expected_sidecar_version}"
        )

    capture = sidecar.get("capture")
    if not isinstance(capture, dict):
        raise RuntimeError("Missing capture object")

    verified = capture.get("verified")
    if not isinstance(verified, bool):
        raise RuntimeError("capture.verified is not boolean")

    classification = str(capture.get("classification", "") or "").strip().upper()
    lightning_type = str(capture.get("type", "") or "").strip().upper()

    if not classification:
        classification = "<BLANK>"

    if not lightning_type:
        lightning_type = "<BLANK>"

    try:
        max_brightness_delta = float(capture["max_brightness_delta"])
        mean_brightness = float(capture["mean_brightness"])
    except (KeyError, TypeError, ValueError) as error:
        raise RuntimeError(
            f"Missing/invalid V{expected_sidecar_version} brightness summary"
        ) from error

    return (
        verified,
        classification,
        lightning_type,
        max_brightness_delta,
        mean_brightness,
    )


def collect_video_files(folder: Path, recursive: bool) -> list[Path]:
    pattern = "**/*.mp4" if recursive else "*.mp4"
    return sorted(folder.glob(pattern))


def print_counter(title: str, counter: Counter[str]) -> None:
    print()
    print(title)

    if not counter:
        print("  (none)")
        return

    width = max(len(key) for key in counter)
    total = sum(counter.values())

    for key, count in sorted(
        counter.items(),
        key=lambda item: (-item[1], item[0]),
    ):
        percent = 100.0 * count / total if total else 0.0
        print(f"  {key:<{width}}  {count:6d}  {percent:6.2f}%")


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Summarize classification and lightning type metadata "
            "for Pi Camera Capture files."
        )
    )

    parser.add_argument(
        "folder",
        type=Path,
        help="Folder containing MP4 capture files and matching JSON sidecars",
    )

    parser.add_argument(
        "--recursive",
        action="store_true",
        help="Include captures in subfolders recursively",
    )

    parser.add_argument(
        "--sidecar-version",
        type=int,
        choices=SUPPORTED_SIDECAR_VERSIONS,
        default=SIDECAR_VERSION,
        help=(
            f"Expected sidecar version. Default: current V{SIDECAR_VERSION}. "
            "Use 7 for historical V7 classification summaries."
        ),
    )

    arguments = parser.parse_args()

    folder = arguments.folder.expanduser()
    expected_sidecar_version = arguments.sidecar_version

    if not folder.is_dir():
        print(f"Folder not found: {folder}")
        return 1

    video_files = collect_video_files(folder, arguments.recursive)

    classification_counts: Counter[str] = Counter()
    type_counts: Counter[str] = Counter()
    verified_counts: Counter[str] = Counter()
    classification_type_counts: Counter[str] = Counter()

    max_delta_values: list[float] = []
    mean_brightness_values: list[float] = []

    valid_count = 0
    missing_sidecar_count = 0
    invalid_sidecar_count = 0
    errors: list[tuple[Path, str]] = []

    for video_path in video_files:
        sidecar_path = video_path.with_suffix(".json")

        if not sidecar_path.is_file():
            missing_sidecar_count += 1
            errors.append((video_path, "matching JSON sidecar not found"))
            continue

        try:
            (
                verified,
                classification,
                lightning_type,
                max_brightness_delta,
                mean_brightness,
            ) = capture_metadata(
                read_sidecar(sidecar_path),
                expected_sidecar_version,
            )
        except RuntimeError as error:
            invalid_sidecar_count += 1
            errors.append((video_path, str(error)))
            continue

        valid_count += 1
        classification_counts[classification] += 1
        type_counts[lightning_type] += 1
        verified_counts["Verified" if verified else "Unverified"] += 1
        classification_type_counts[
            f"{classification} / {lightning_type}"
        ] += 1
        max_delta_values.append(max_brightness_delta)
        mean_brightness_values.append(mean_brightness)

    print(f"Folder: {folder}")
    print(f"Expected sidecar version: V{expected_sidecar_version}")
    print(f"Captures found: {len(video_files)}")
    print(f"Valid V{expected_sidecar_version} captures: {valid_count}")
    print(f"Total classified captures: {sum(classification_counts.values())}")
    print(f"Missing sidecars: {missing_sidecar_count}")
    print(f"Invalid sidecars: {invalid_sidecar_count}")

    print_counter("Verification:", verified_counts)
    print_counter("Classifications:", classification_counts)
    print_counter("Types:", type_counts)
    print_counter(
        "Classification / Type combinations:",
        classification_type_counts,
    )

    if max_delta_values:
        print()
        print("Brightness summaries:")
        print(
            "  max_brightness_delta  "
            f"min={min(max_delta_values):.1f}  "
            f"mean={sum(max_delta_values) / len(max_delta_values):.1f}  "
            f"max={max(max_delta_values):.1f}"
        )
        print(
            "  mean_brightness       "
            f"min={min(mean_brightness_values):.1f}  "
            f"mean={sum(mean_brightness_values) / len(mean_brightness_values):.1f}  "
            f"max={max(mean_brightness_values):.1f}"
        )

    if errors:
        print()
        print("Problems:")
        for video_path, detail in errors:
            print(f"  {video_path}: {detail}")

    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
