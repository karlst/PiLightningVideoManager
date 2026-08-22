"""
@file buildCaptureIndex.py

@brief Build the static G Site captures.json catalog from published MP4/JSON pairs.

The G Site is front-end only. It cannot scan a server directory at runtime, so
captures.json acts as the catalog used by captureGallery.js. This utility scans
a directory containing published capture MP4s and their matching JSON sidecars,
extracts only the small amount of metadata needed by the gallery, and writes a
captures.json index.

The sidecar remains the authoritative source for detailed capture information.

Typical use from the VideoManager repository root:

    python tools/buildCaptureIndex.py web_viewer/captures

By default the index is written to:

    web_viewer/captures.json

You may override the output location with --output.

Only MP4 files with a matching same-stem JSON sidecar are indexed.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any


DEFAULT_OUTPUT_PATH = Path("web_viewer") / "captures.json"


def read_sidecar(sidecar_path: Path) -> dict[str, Any]:
    try:
        data = json.loads(
            sidecar_path.read_text(
                encoding="utf-8"
            )
        )
    except OSError as error:
        raise RuntimeError(
            f"Unable to read {sidecar_path.name}: {error}"
        ) from error
    except json.JSONDecodeError as error:
        raise RuntimeError(
            f"Invalid JSON in {sidecar_path.name}: {error}"
        ) from error

    if not isinstance(data, dict):
        raise RuntimeError(
            f"Sidecar must contain a JSON object: {sidecar_path.name}"
        )

    return data


def original_sensitivity(sidecar: dict[str, Any]) -> str:
    candidate = sidecar.get("candidate")

    if isinstance(candidate, dict):
        config = candidate.get("config")

        if isinstance(config, dict):
            sensitivity = config.get("sensitivity")

            if sensitivity:
                return str(sensitivity).lower()

    sensitivity = sidecar.get("sensitivity")

    if sensitivity:
        return str(sensitivity).lower()

    return ""


def original_solution(
    sidecar: dict[str, Any],
    sensitivity: str,
) -> str:
    results = sidecar.get("sensitivity_results")

    if (
        sensitivity and
        isinstance(results, dict)
    ):
        result = results.get(sensitivity)

        if isinstance(result, dict):
            category = result.get("solution_category")

            if category:
                return str(category).upper()

    for key in (
        "solution_category",
        "classification",
        "solution",
    ):
        value = sidecar.get(key)

        if value:
            return str(value).upper()

    return ""


def capture_time_utc(sidecar: dict[str, Any]) -> str:
    capture = sidecar.get("capture")

    if isinstance(capture, dict):
        for key in (
            "start_utc",
            "saved_utc",
            "end_utc",
        ):
            value = capture.get(key)

            if value:
                return str(value)

    for key in (
        "capture_start_utc",
        "saved_utc",
        "trigger_utc",
    ):
        value = sidecar.get(key)

        if value:
            return str(value)

    candidate = sidecar.get("candidate")

    if isinstance(candidate, dict):
        value = candidate.get("trigger_utc")

        if value:
            return str(value)

    return ""


def site_name(sidecar: dict[str, Any]) -> str:
    camera = sidecar.get("camera")

    if isinstance(camera, dict):
        value = camera.get("site_name")

        if value:
            return str(value)

    value = sidecar.get("site_name")

    if value:
        return str(value)

    return ""


def build_entry(
    mp4_path: Path,
    sidecar_path: Path,
    capture_directory: Path,
) -> dict[str, Any]:
    sidecar = read_sidecar(
        sidecar_path
    )

    sensitivity = original_sensitivity(
        sidecar
    )

    solution = original_solution(
        sidecar,
        sensitivity,
    )

    relative_mp4 = mp4_path.relative_to(
        capture_directory
    ).as_posix()

    relative_json = sidecar_path.relative_to(
        capture_directory
    ).as_posix()

    return {
        "capture_time_utc":
            capture_time_utc(
                sidecar
            ),

        "site_name":
            site_name(
                sidecar
            ),

        "sensitivity":
            sensitivity,

        "solution":
            solution,

        "video_name":
            mp4_path.name,

        "video_url":
            f"captures/{relative_mp4}",

        "sidecar_url":
            f"captures/{relative_json}",
    }


def build_index(
    capture_directory: Path,
) -> tuple[list[dict[str, Any]], list[str]]:
    entries: list[
        dict[str, Any]
    ] = []

    warnings: list[
        str
    ] = []

    for mp4_path in sorted(
        capture_directory.glob("*.mp4")
    ):
        sidecar_path = mp4_path.with_suffix(
            ".json"
        )

        if not sidecar_path.is_file():
            warnings.append(
                f"Skipping {mp4_path.name}: matching JSON sidecar not found"
            )
            continue

        try:
            entry = build_entry(
                mp4_path,
                sidecar_path,
                capture_directory,
            )
        except RuntimeError as error:
            warnings.append(
                f"Skipping {mp4_path.name}: {error}"
            )
            continue

        entries.append(
            entry
        )

    entries.sort(
        key=lambda entry: str(
            entry.get(
                "capture_time_utc",
                ""
            )
        ),
        reverse=True,
    )

    return (
        entries,
        warnings,
    )


def write_index(
    output_path: Path,
    entries: list[dict[str, Any]],
) -> None:
    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    document = {
        "version": 1,
        "captures": entries,
    }

    output_path.write_text(
        json.dumps(
            document,
            indent=4,
        ) + "\n",
        encoding="utf-8",
    )


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Build the G Site captures.json catalog from a directory "
            "of MP4/JSON capture pairs."
        )
    )

    parser.add_argument(
        "capture_directory",
        type=Path,
        help=(
            "Directory containing published MP4 files and matching JSON sidecars"
        ),
    )

    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT_PATH,
        help=(
            "Output captures.json path "
            f"(default: {DEFAULT_OUTPUT_PATH})"
        ),
    )

    return parser


def main() -> int:
    parser = build_argument_parser()

    arguments = parser.parse_args()

    capture_directory = (
        arguments.capture_directory.resolve()
    )

    if not capture_directory.is_dir():
        parser.error(
            f"Capture directory not found: {capture_directory}"
        )

    entries, warnings = build_index(
        capture_directory
    )

    write_index(
        arguments.output,
        entries,
    )

    for warning in warnings:
        print(
            f"WARNING: {warning}"
        )

    print(
        f"Wrote {arguments.output}: {len(entries)} capture(s)"
    )

    return 0


if __name__ == "__main__":
    sys.exit(
        main()
    )
