r"""
@file migrate_field_v4_for_s3.py

@brief One-off migration/classification tool for the historical field-camera V4 batch.

This tool intentionally leaves the source collection untouched.

For each complete V4 MP4/JSON pair:
    1. Reject/skip manual captures.
    2. Patch the known camera latitude, longitude, and bearing.
    3. Recalculate the Search Bounding Box using the source HFOV and source
       minimum/maximum search ranges.
    4. Run the frozen production logistic-v1 classifier through the current
       tools.migrate_capture_files V4->V8 migration code.
    5. Force the current V8 classification to the logistic-v1 result so this
       one-off batch is split strictly by the current model, not by legacy
       SolutionFilter/adjudication metadata.
    6. Copy the migrated MP4/JSON pair into:
           <output>/Flashes/
           <output>/Anomalies/

FLASH outputs remain unverified for human review.
ANOMALY outputs are verified, consistent with current V8 production policy.

The resulting folders are staging folders for later S3 upload.

Example:
    python -m tools.migrate_field_v4_for_s3 E:\FieldCaptures E:\FieldV8 --recursive

Dry run:
    python -m tools.migrate_field_v4_for_s3 E:\FieldCaptures E:\FieldV8 --recursive --dry-run
"""

from __future__ import annotations

import argparse
import copy
import math
from pathlib import Path
import shutil
import sys
from typing import Any


# ---------------------------------------------------------------------------
# ONE-OFF FIELD CAMERA PATCH CONSTANTS
# ---------------------------------------------------------------------------

PATCH_LATITUDE_DEGREES = 35.18123
PATCH_LONGITUDE_DEGREES = -111.50162
PATCH_BEARING_DEGREES = 268.0

EXPECTED_SOURCE_SIDECAR_VERSION = 4

FLASH_FOLDER_NAME = "Flashes"
ANOMALY_FOLDER_NAME = "Anomalies"

# Keep the source sidecar's HFOV and search-distance limits. Only the camera
# position/bearing are hard-coded for this one-off migration.


REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from common.classification_model import CLASSIFICATION_ANOMALY
from common.classification_model import CLASSIFICATION_FLASH
from common.classification_model import CLASSIFICATION_MODEL_NAME

from tools.migrate_capture_files import compact_frame_records
from tools.migrate_capture_files import migrate_sidecar
from tools.migrate_capture_files import read_sidecar
from tools.migrate_capture_files import strip_capture_prefix
from tools.migrate_capture_files import validate_migrated_sidecar


# ---------------------------------------------------------------------------
# Search Bounding Box math.
#
# This is the same conservative spherical-Earth geometry currently used by
# Pi Camera Capture's camera configuration / sidecar-rebuild code. It is kept
# here deliberately so this one-off tool has no dependency on runtime camera
# configuration files.
# ---------------------------------------------------------------------------

def destination_point(
    latitude_degrees: float,
    longitude_degrees: float,
    bearing_degrees: float,
    distance_miles: float,
) -> tuple[float, float]:
    earth_radius_miles = 3958.7613

    latitude_radians = math.radians(latitude_degrees)
    longitude_radians = math.radians(longitude_degrees)
    bearing_radians = math.radians(bearing_degrees)
    angular_distance = distance_miles / earth_radius_miles

    destination_latitude = math.asin(
        math.sin(latitude_radians) * math.cos(angular_distance)
        + math.cos(latitude_radians)
        * math.sin(angular_distance)
        * math.cos(bearing_radians)
    )

    destination_longitude = longitude_radians + math.atan2(
        math.sin(bearing_radians)
        * math.sin(angular_distance)
        * math.cos(latitude_radians),
        math.cos(angular_distance)
        - math.sin(latitude_radians) * math.sin(destination_latitude),
    )

    normalized_longitude = (
        (math.degrees(destination_longitude) + 540.0) % 360.0
    ) - 180.0

    return math.degrees(destination_latitude), normalized_longitude


def bearing_in_sector(
    bearing_degrees: float,
    left_degrees: float,
    right_degrees: float,
) -> bool:
    bearing = bearing_degrees % 360.0
    left = left_degrees % 360.0
    right = right_degrees % 360.0

    if left <= right:
        return left <= bearing <= right

    return bearing >= left or bearing <= right


def build_search_bounding_box(
    latitude_degrees: float,
    longitude_degrees: float,
    bearing_degrees: float,
    hfov_degrees: float,
    minimum_range_miles: float,
    maximum_range_miles: float,
) -> dict[str, float]:
    minimum_range = max(0.0, float(minimum_range_miles))
    maximum_range = max(minimum_range, float(maximum_range_miles))

    half_fov = max(
        0.0,
        min(
            180.0,
            float(hfov_degrees) / 2.0,
        ),
    )

    left_bearing = (float(bearing_degrees) - half_fov) % 360.0
    right_bearing = (float(bearing_degrees) + half_fov) % 360.0

    bearings = [
        left_bearing,
        float(bearing_degrees) % 360.0,
        right_bearing,
    ]

    for cardinal_bearing in (0.0, 90.0, 180.0, 270.0):
        if bearing_in_sector(
            cardinal_bearing,
            left_bearing,
            right_bearing,
        ):
            bearings.append(cardinal_bearing)

    points: list[tuple[float, float]] = []

    for range_miles in (minimum_range, maximum_range):
        for search_bearing in bearings:
            points.append(
                destination_point(
                    latitude_degrees,
                    longitude_degrees,
                    search_bearing,
                    range_miles,
                )
            )

    latitudes = [point[0] for point in points]
    longitudes = [point[1] for point in points]

    return {
        "minimum_range_miles": minimum_range,
        "maximum_range_miles": maximum_range,
        "min_latitude_degrees": round(min(latitudes), 7),
        "max_latitude_degrees": round(max(latitudes), 7),
        "min_longitude_degrees": round(min(longitudes), 7),
        "max_longitude_degrees": round(max(longitudes), 7),
    }


def compact_bounding_box(box: dict[str, Any]) -> dict[str, list[float]]:
    return {
        "range": [
            float(box["minimum_range_miles"]),
            float(box["maximum_range_miles"]),
        ],
        "lat": [
            float(box["min_latitude_degrees"]),
            float(box["max_latitude_degrees"]),
        ],
        "lon": [
            float(box["min_longitude_degrees"]),
            float(box["max_longitude_degrees"]),
        ],
    }


def source_search_ranges(camera: dict[str, Any]) -> tuple[float, float]:
    box = camera.get("search_bounding_box")
    if not isinstance(box, dict):
        raise RuntimeError(
            "Source camera.search_bounding_box is missing; "
            "cannot preserve search range without guessing"
        )

    if "range" in box:
        values = box["range"]
        if not isinstance(values, (list, tuple)) or len(values) != 2:
            raise RuntimeError("Source camera.search_bounding_box.range is invalid")
        minimum_range = float(values[0])
        maximum_range = float(values[1])
    else:
        try:
            minimum_range = float(box["minimum_range_miles"])
            maximum_range = float(box["maximum_range_miles"])
        except (KeyError, TypeError, ValueError) as error:
            raise RuntimeError(
                "Source camera.search_bounding_box does not contain valid "
                "minimum/maximum ranges"
            ) from error

    if not math.isfinite(minimum_range) or not math.isfinite(maximum_range):
        raise RuntimeError("Source search ranges are not finite")
    if minimum_range < 0.0 or maximum_range < minimum_range:
        raise RuntimeError(
            f"Source search range is invalid: {minimum_range}..{maximum_range}"
        )

    return minimum_range, maximum_range


def patched_source_sidecar(old_sidecar: dict[str, Any]) -> dict[str, Any]:
    version = old_sidecar.get("sidecar_version")
    if version != EXPECTED_SOURCE_SIDECAR_VERSION:
        raise RuntimeError(
            f"Expected V{EXPECTED_SOURCE_SIDECAR_VERSION} sidecar, got {version!r}"
        )

    working = copy.deepcopy(old_sidecar)

    camera = working.get("camera")
    if not isinstance(camera, dict):
        raise RuntimeError("Source sidecar is missing camera metadata")

    try:
        hfov_degrees = float(camera["hfov_degrees"])
    except (KeyError, TypeError, ValueError) as error:
        raise RuntimeError(
            "Source camera.hfov_degrees is missing/invalid; refusing to guess"
        ) from error

    if not math.isfinite(hfov_degrees) or not 0.0 < hfov_degrees <= 360.0:
        raise RuntimeError(
            f"Source camera.hfov_degrees is invalid: {hfov_degrees!r}"
        )

    minimum_range, maximum_range = source_search_ranges(camera)

    new_box = build_search_bounding_box(
        PATCH_LATITUDE_DEGREES,
        PATCH_LONGITUDE_DEGREES,
        PATCH_BEARING_DEGREES,
        hfov_degrees,
        minimum_range,
        maximum_range,
    )

    camera["latitude_degrees"] = PATCH_LATITUDE_DEGREES
    camera["longitude_degrees"] = PATCH_LONGITUDE_DEGREES
    camera["bearing_degrees"] = PATCH_BEARING_DEGREES
    camera["search_bounding_box"] = new_box

    # V4 historically duplicated this block at top level. The current V8
    # migration drops the duplicate, but keep the temporary source internally
    # consistent before migration.
    working["search_bounding_box"] = copy.deepcopy(new_box)

    # This one-off operation is explicitly meant to show what logistic-v1 says,
    # regardless of any historical top-level adjudication token.
    working.pop("classification", None)
    working.pop("verified", None)
    working.pop("initial_classification", None)
    working.pop("type", None)

    return working


def require_auto_trigger(sidecar: dict[str, Any]) -> int:
    candidate = sidecar.get("candidate")
    if not isinstance(candidate, dict):
        raise RuntimeError("Source sidecar is missing candidate metadata")

    trigger_type = str(candidate.get("trigger_type", "") or "").strip().lower()
    if trigger_type == "manual":
        raise RuntimeError("MANUAL_CAPTURE")
    if not trigger_type:
        raise RuntimeError("Source candidate.trigger_type is blank")

    try:
        trigger_index = int(candidate["trigger_frame_index"])
    except (KeyError, TypeError, ValueError) as error:
        raise RuntimeError(
            "Auto-triggered source has no valid candidate.trigger_frame_index"
        ) from error

    records = sidecar.get("frame_records")
    if not isinstance(records, list) or not records:
        raise RuntimeError("Source frame_records are missing")

    if not 0 <= trigger_index < len(records):
        raise RuntimeError(
            f"Candidate trigger frame {trigger_index} is outside "
            f"{len(records)} frame_records"
        )

    return trigger_index


def force_logistic_classification(migrated: dict[str, Any]) -> None:
    capture = migrated.get("capture")
    if not isinstance(capture, dict):
        raise RuntimeError("Migrated sidecar is missing capture metadata")

    initial = str(
        capture.get("initial_classification", "") or ""
    ).strip().upper()

    if initial not in {CLASSIFICATION_FLASH, CLASSIFICATION_ANOMALY}:
        raise RuntimeError(
            f"Migrated logistic classification is invalid: {initial or '<blank>'}"
        )

    capture["classification"] = initial
    capture["verified"] = initial == CLASSIFICATION_ANOMALY
    capture["type"] = "UK"

    if str(capture.get("classification_model", "") or "") != CLASSIFICATION_MODEL_NAME:
        raise RuntimeError("Migrated sidecar does not contain logistic-v1 provenance")

    # This V4 field-camera batch has no durable human legacy label. Prevent a
    # historical SolutionFilter label from being represented as human truth.
    migration = migrated.get("migration")
    if isinstance(migration, dict):
        migration.pop("legacy_classification", None)


def validate_geometry(
    migrated: dict[str, Any],
    source_hfov: float,
    source_minimum_range: float,
    source_maximum_range: float,
) -> None:
    camera = migrated.get("camera")
    if not isinstance(camera, dict):
        raise RuntimeError("Migrated camera metadata is missing")

    if float(camera.get("latitude_degrees")) != PATCH_LATITUDE_DEGREES:
        raise RuntimeError("Migrated latitude patch failed")
    if float(camera.get("longitude_degrees")) != PATCH_LONGITUDE_DEGREES:
        raise RuntimeError("Migrated longitude patch failed")
    if float(camera.get("bearing_degrees")) != PATCH_BEARING_DEGREES:
        raise RuntimeError("Migrated bearing patch failed")

    expected_box = compact_bounding_box(
        build_search_bounding_box(
            PATCH_LATITUDE_DEGREES,
            PATCH_LONGITUDE_DEGREES,
            PATCH_BEARING_DEGREES,
            source_hfov,
            source_minimum_range,
            source_maximum_range,
        )
    )

    if camera.get("search_bounding_box") != expected_box:
        raise RuntimeError(
            "Migrated Search Bounding Box does not match recalculated geometry"
        )


def migrated_capture(
    old_sidecar: dict[str, Any],
) -> dict[str, Any]:
    require_auto_trigger(old_sidecar)

    old_camera = old_sidecar.get("camera")
    if not isinstance(old_camera, dict):
        raise RuntimeError("Source sidecar is missing camera metadata")

    try:
        source_hfov = float(old_camera["hfov_degrees"])
    except (KeyError, TypeError, ValueError) as error:
        raise RuntimeError("Source camera.hfov_degrees is invalid") from error

    minimum_range, maximum_range = source_search_ranges(old_camera)

    patched = patched_source_sidecar(old_sidecar)

    # Use the current authoritative migrator for V8 construction and the exact
    # current production classifier/model.
    migrated = migrate_sidecar(
        patched,
        source_classification=None,
    )

    force_logistic_classification(migrated)

    # Validate V8 structure/model fields using the current migration validator.
    # We intentionally do not compare camera metadata against the original
    # source because geometry is the explicit purpose of this one-off patch.
    validate_migrated_sidecar(migrated)

    validate_geometry(
        migrated,
        source_hfov,
        minimum_range,
        maximum_range,
    )

    if migrated.get("frame_records") != compact_frame_records(
        old_sidecar["frame_records"]
    ):
        raise RuntimeError("Migration changed frame brightness/timing records")

    return migrated


def output_pair_paths(
    source_video: Path,
    output_root: Path,
    migrated: dict[str, Any],
) -> tuple[Path, Path]:
    capture = migrated["capture"]
    classification = str(capture["classification"]).strip().upper()

    if classification == CLASSIFICATION_FLASH:
        folder = output_root / FLASH_FOLDER_NAME
    elif classification == CLASSIFICATION_ANOMALY:
        folder = output_root / ANOMALY_FOLDER_NAME
    else:
        raise RuntimeError(
            f"Unexpected migrated classification: {classification}"
        )

    suffix = strip_capture_prefix(source_video.stem)
    output_video = folder / f"capture_{suffix}{source_video.suffix.lower()}"
    output_json = output_video.with_suffix(".json")
    return output_video, output_json


def write_pair(
    source_video: Path,
    destination_video: Path,
    destination_json: Path,
    migrated: dict[str, Any],
) -> None:
    if destination_video.exists() or destination_json.exists():
        raise RuntimeError(
            f"Destination pair already exists: {destination_video.stem}"
        )

    destination_video.parent.mkdir(parents=True, exist_ok=True)

    temp_json = destination_json.with_name(
        destination_json.name + ".migration.tmp"
    )

    if temp_json.exists():
        raise RuntimeError(f"Temporary output already exists: {temp_json}")

    try:
        temp_json.write_text(
            __import__("json").dumps(migrated, indent=4) + "\n",
            encoding="utf-8",
        )

        # Parse what was actually staged before copying/installing the pair.
        staged = read_sidecar(temp_json)
        validate_migrated_sidecar(staged)

        shutil.copy2(source_video, destination_video)
        temp_json.replace(destination_json)

    except Exception:
        destination_video.unlink(missing_ok=True)
        destination_json.unlink(missing_ok=True)
        temp_json.unlink(missing_ok=True)
        raise


def collect_videos(
    source: Path,
    recursive: bool,
    output_root: Path,
) -> list[Path]:
    if source.is_file():
        candidate = source
        if candidate.suffix.lower() == ".json":
            candidate = candidate.with_suffix(".mp4")
        if candidate.suffix.lower() != ".mp4":
            raise RuntimeError("Source file must be an MP4 or JSON")
        if not candidate.is_file():
            raise RuntimeError(f"Matching MP4 not found: {candidate}")
        return [candidate]

    if not source.is_dir():
        raise RuntimeError(f"Source not found: {source}")

    pattern = "**/*.mp4" if recursive else "*.mp4"
    videos: list[Path] = []

    for video in sorted(source.glob(pattern)):
        try:
            video.resolve().relative_to(output_root.resolve())
            continue
        except ValueError:
            pass
        videos.append(video)

    return videos


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "One-off V4 field-camera migration: patch geometry, classify with "
            "logistic-v1, and copy V8 pairs into Flashes/Anomalies folders."
        )
    )

    parser.add_argument(
        "source",
        type=Path,
        help="Source V4 capture folder, MP4, or JSON",
    )
    parser.add_argument(
        "output",
        type=Path,
        help="Output staging folder; Flashes/ and Anomalies/ are created beneath it",
    )
    parser.add_argument(
        "--recursive",
        action="store_true",
        help="Process source subfolders recursively",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Classify/validate and report without writing output files",
    )

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    source = args.source.expanduser()
    output_root = args.output.expanduser()

    if source.is_dir():
        try:
            output_root.resolve().relative_to(source.resolve())
            if not args.recursive:
                pass
        except ValueError:
            pass

    try:
        videos = collect_videos(source, args.recursive, output_root)
    except Exception as error:
        print(f"ERROR: {error}")
        return 1

    counts = {
        CLASSIFICATION_FLASH: 0,
        CLASSIFICATION_ANOMALY: 0,
        "manual_skipped": 0,
        "duplicate_skipped": 0,
        "failed": 0,
    }

    print(
        "Geometry patch: "
        f"lat={PATCH_LATITUDE_DEGREES}, "
        f"lon={PATCH_LONGITUDE_DEGREES}, "
        f"bearing={PATCH_BEARING_DEGREES}"
    )
    print(f"Model: {CLASSIFICATION_MODEL_NAME}")
    print(f"Captures found: {len(videos)}")
    print()

    for video_path in videos:
        sidecar_path = video_path.with_suffix(".json")

        if not sidecar_path.is_file():
            counts["failed"] += 1
            print(f"FAIL     {video_path.name}: matching JSON not found")
            continue

        try:
            old_sidecar = read_sidecar(sidecar_path)
            migrated = migrated_capture(old_sidecar)

            classification = migrated["capture"]["classification"]
            confidence = float(migrated["capture"]["initial_confidence"])

            destination_video, destination_json = output_pair_paths(
                video_path,
                output_root,
                migrated,
            )

            if destination_video.exists() or destination_json.exists():
                counts["duplicate_skipped"] += 1
                print(
                    f"SKIP DUP {video_path.name} -> "
                    f"{destination_video.parent.name}/{destination_video.name}"
                )
                continue

            counts[classification] += 1

            print(
                f"{classification:<7}  "
                f"confidence={confidence:.6f}  "
                f"{video_path.name}"
            )
            print(
                f"         -> "
                f"{destination_video.parent.name}/{destination_video.name}"
            )

            if not args.dry_run:
                write_pair(
                    video_path,
                    destination_video,
                    destination_json,
                    migrated,
                )

        except RuntimeError as error:
            if str(error) == "MANUAL_CAPTURE":
                counts["manual_skipped"] += 1
                print(f"SKIP MANUAL  {video_path.name}")
            else:
                counts["failed"] += 1
                print(f"FAIL     {video_path.name}: {error}")

        except Exception as error:
            counts["failed"] += 1
            print(f"FAIL     {video_path.name}: {error}")

    print()
    print("Dry run summary:" if args.dry_run else "Summary:")
    print(f"  Captures found:    {len(videos)}")
    print(f"  Flashes:           {counts[CLASSIFICATION_FLASH]}")
    print(f"  Anomalies:         {counts[CLASSIFICATION_ANOMALY]}")
    print(f"  Manual skipped:    {counts['manual_skipped']}")
    print(f"  Duplicate skipped: {counts['duplicate_skipped']}")
    print(f"  Failed:            {counts['failed']}")

    return 0 if counts["failed"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
