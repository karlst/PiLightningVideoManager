"""
@file rebuild_sidecars.py

@brief Rebuild missing sidecars and migrate older sidecars to the current schema.

RebuildSidecars is the batch maintenance tool for Pi Camera Capture sidecars.
It supports one MP4, one directory, or a directory tree and runs on Windows,
Linux, or Raspberry Pi when the normal project Python dependencies are
available.

For each MP4:

    * Missing sidecar:
        Reconstruct a current sidecar from the encoded MP4 as far as possible.

    * Older/incomplete sidecar:
        Preserve the original JSON as OldTrigger_....json, retain historical
        metadata that cannot be recovered from the MP4, reconstruct current
        analysis, and write a current sidecar under the normal filename.

    * Current complete sidecar:
        Leave it unchanged.

The current schema stores High, Medium, and Low CandidateFinder/SolutionFilter
results so the P Site and static G Site can switch sensitivity without running
analysis in the browser.

The MP4 is never modified.

Examples:

    python rebuild_sidecars.py trigger_20260821T120000Z.mp4
    python rebuild_sidecars.py C:\\Lightning\\true_flashes
    python rebuild_sidecars.py /home/karlst/elpData3709/captures --recursive
    python rebuild_sidecars.py C:\\Lightning --recursive --dry-run

Optional camera/site arguments fill metadata that is missing from an older
sidecar. Existing sidecar values take precedence unless an explicit command
line override is supplied.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime
from datetime import timezone
import json
import math
from pathlib import Path
import re
import sys
from typing import Any

# tools/rebuild_sidecars.py lives one directory below the repository root.
# Add that root to Python's module search path so imports such as common.*
# and video_analyzer.* work when this script is launched directly:
#
#     python tools/rebuild_sidecars.py ...
REPO_ROOT = Path(__file__).resolve().parent.parent

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import cv2
import numpy as np

from common.candidate_config import get_sensitivity_config
from common.candidate_finder import CandidateFinder
from video_analyzer.capture_data import analyze_clip
from video_analyzer.capture_data import build_bright_pixel_fraction
from video_analyzer.capture_data import read_frame_info
from video_analyzer.solution_config import SOLUTION_CONFIG
from video_analyzer.solution_filter import SolutionFilter
from video_analyzer.solution_filter import failed_candidate_result


CURRENT_SIDECAR_VERSION = 2
TOOL_NAME = "RebuildSidecars"
DEFAULT_SITE_NAME = "Flagstaff"
DEFAULT_MINIMUM_RANGE_MILES = 1.0
DEFAULT_MAXIMUM_RANGE_MILES = 25.0

SENSITIVITY_NAMES = (
    "high",
    "medium",
    "low",
)


# ## Return current UTC text for migration/reconstruction provenance.
def now_utc_text() -> str:
    return datetime.now(
        timezone.utc
    ).isoformat(
        timespec="seconds"
    ).replace(
        "+00:00",
        "Z"
    )


# ## Read and validate one existing JSON sidecar.
def read_sidecar(
    sidecar_path: Path,
) -> dict[str, Any]:
    try:
        data = json.loads(
            sidecar_path.read_text(
                encoding="utf-8"
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
        dict
    ):
        raise RuntimeError(
            "Sidecar JSON must contain an object"
        )

    return data


# ## Return a current nested value with fallback to a legacy flat field.
def sidecar_value(
    sidecar: dict[str, Any] | None,
    section_name: str,
    key: str,
    legacy_key: str | None = None,
    default: Any = None,
) -> Any:
    if sidecar is None:
        return default

    section = sidecar.get(
        section_name
    )

    if (
        isinstance(
            section,
            dict
        ) and
        key in section
    ):
        return section.get(
            key,
            default
        )

    fallback_key = (
        legacy_key
        if legacy_key is not None
        else key
    )

    return sidecar.get(
        fallback_key,
        default
    )


# ## Return a usable numeric value or None.
def optional_float(
    value: Any,
) -> float | None:
    if (
        value is None or
        value == ""
    ):
        return None

    try:
        number = float(
            value
        )
    except (
        TypeError,
        ValueError,
    ):
        return None

    if not math.isfinite(
        number
    ):
        return None

    return number


# ## Return a usable integer value or None.
def optional_int(
    value: Any,
) -> int | None:
    if (
        value is None or
        value == ""
    ):
        return None

    try:
        return int(
            value
        )
    except (
        TypeError,
        ValueError,
    ):
        return None


# ## Recover the ClipWriter save time from a standard trigger filename.
def saved_utc_from_filename(
    video_path: Path,
) -> str:
    match = re.search(
        r"trigger_(\d{8})T(\d{6})Z",
        video_path.stem,
        flags=re.IGNORECASE,
    )

    if match is None:
        return ""

    try:
        parsed = datetime.strptime(
            (
                match.group(1) +
                match.group(2)
            ),
            "%Y%m%d%H%M%S",
        ).replace(
            tzinfo=timezone.utc
        )
    except ValueError:
        return ""

    return parsed.isoformat(
        timespec="seconds"
    ).replace(
        "+00:00",
        "Z"
    )


# ## Convert ffprobe frame timing to capture-relative milliseconds.
def build_offsets_ms(
    frame_info: list[dict[str, Any]],
    frame_count: int,
    nominal_fps: float,
) -> list[float]:
    raw_times: list[float] = []

    for frame_index in range(
        frame_count
    ):
        frame_time = float(
            "nan"
        )

        if frame_index < len(
            frame_info
        ):
            try:
                frame_time = float(
                    frame_info[
                        frame_index
                    ][
                        "best_effort_timestamp_time"
                    ]
                )
            except (
                KeyError,
                TypeError,
                ValueError,
            ):
                pass

        raw_times.append(
            frame_time
        )

    if (
        raw_times and
        np.isfinite(
            raw_times[0]
        ) and
        all(
            np.isfinite(
                value
            )
            for value in raw_times
        )
    ):
        first_time = raw_times[
            0
        ]

        return [
            round(
                (
                    value -
                    first_time
                ) *
                1000.0,
                3
            )
            for value in raw_times
        ]

    if nominal_fps <= 0.0:
        nominal_fps = 260.0

    return [
        round(
            (
                frame_index /
                nominal_fps
            ) *
            1000.0,
            3
        )
        for frame_index in range(
            frame_count
        )
    ]


# ## Read nominal video geometry without another full decode.
def read_video_geometry(
    video_path: Path,
) -> tuple[float, int, int]:
    capture = cv2.VideoCapture(
        str(
            video_path
        )
    )

    if not capture.isOpened():
        raise RuntimeError(
            f"OpenCV could not open: {video_path}"
        )

    nominal_fps = float(
        capture.get(
            cv2.CAP_PROP_FPS
        )
    )

    width = int(
        capture.get(
            cv2.CAP_PROP_FRAME_WIDTH
        )
    )

    height = int(
        capture.get(
            cv2.CAP_PROP_FRAME_HEIGHT
        )
    )

    capture.release()

    return (
        nominal_fps,
        width,
        height,
    )


# ## Build Pi-metric arrays from an existing sidecar when they are available.
def build_preserved_pi_metrics(
    old_sidecar: dict[str, Any] | None,
    replay_brightness: np.ndarray,
    replay_brightness_delta: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    frame_count = len(
        replay_brightness
    )

    brightness = np.array(
        replay_brightness,
        copy=True
    )

    brightness_delta = np.array(
        replay_brightness_delta,
        copy=True
    )

    if old_sidecar is None:
        return (
            brightness,
            brightness_delta,
        )

    records = old_sidecar.get(
        "frame_records",
        []
    )

    if not isinstance(
        records,
        list
    ):
        return (
            brightness,
            brightness_delta,
        )

    for list_index, record in enumerate(
        records
    ):
        if not isinstance(
            record,
            dict
        ):
            continue

        frame_index = optional_int(
            record.get(
                "frame_index",
                list_index
            )
        )

        if (
            frame_index is None or
            not 0 <= frame_index < frame_count
        ):
            continue

        pi_brightness = optional_float(
            record.get(
                "mean_brightness"
            )
        )

        pi_delta = optional_float(
            record.get(
                "brightness_delta_adjacent"
            )
        )

        if pi_brightness is not None:
            brightness[
                frame_index
            ] = pi_brightness

        if pi_delta is not None:
            brightness_delta[
                frame_index
            ] = pi_delta

    return (
        brightness,
        brightness_delta,
    )


# ## Replay CandidateFinder and SolutionFilter for all three standard sensitivities.
def build_sensitivity_results(
    replay_brightness: np.ndarray,
    replay_brightness_delta: np.ndarray,
    positive_delta_histograms: np.ndarray,
    solution_brightness: np.ndarray,
    solution_brightness_delta: np.ndarray,
    offsets_ms: list[float],
) -> dict[str, dict[str, Any]]:
    results: dict[
        str,
        dict[str, Any]
    ] = {}

    for sensitivity in SENSITIVITY_NAMES:
        config = get_sensitivity_config(
            sensitivity
        )

        bright_pixel_fraction = (
            build_bright_pixel_fraction(
                positive_delta_histograms,
                config.
                    candidate_bright_pixel_delta_threshold,
            )
        )

        candidate_finder = CandidateFinder(
            config
        )

        trigger_frame_index = None
        trigger_reason = ""

        for frame_index in range(
            len(
                replay_brightness
            )
        ):
            metric = {
                "mean_brightness":
                    float(
                        replay_brightness[
                            frame_index
                        ]
                    ),

                "brightness_delta_adjacent":
                    float(
                        replay_brightness_delta[
                            frame_index
                        ]
                    ),

                "bright_pixel_fraction":
                    float(
                        bright_pixel_fraction[
                            frame_index
                        ]
                    ),
            }

            found, reason = (
                candidate_finder.evaluate(
                    metric
                )
            )

            if found:
                trigger_frame_index = (
                    frame_index
                )

                trigger_reason = reason
                break

        if trigger_frame_index is None:
            solution_result = (
                failed_candidate_result()
            )

            solution_reason = (
                "CandidateFinder found no trigger at "
                f"{sensitivity.capitalize()} sensitivity; "
                "SolutionFilter was not run."
            )
        else:
            solution_result = (
                SolutionFilter(
                    SOLUTION_CONFIG
                ).evaluate(
                    solution_brightness,
                    solution_brightness_delta,
                    trigger_frame_index,
                    trigger_reason,
                )
            )

            solution_reason = (
                solution_result.reason
            )

        trigger_frame_number = None
        trigger_offset_ms = None

        if trigger_frame_index is not None:
            trigger_frame_number = (
                trigger_frame_index +
                1
            )

            if trigger_frame_index < len(
                offsets_ms
            ):
                trigger_offset_ms = (
                    offsets_ms[
                        trigger_frame_index
                    ]
                )

        config_dict = asdict(
            config
        )

        results[
            sensitivity
        ] = {
            "candidate_config":
                config_dict,

            "candidate_found":
                trigger_frame_index
                is not None,

            "trigger_frame_index":
                trigger_frame_index,

            "trigger_frame_number":
                trigger_frame_number,

            "trigger_offset_ms":
                trigger_offset_ms,

            "trigger_reason":
                trigger_reason,

            "solution_category":
                solution_result.category,

            "solution_reason":
                solution_reason,
        }

    return results


# ## Build current frame records while retaining old Pi timing/brightness when present.
def build_frame_records(
    old_sidecar: dict[str, Any] | None,
    replay_brightness: np.ndarray,
    replay_brightness_delta: np.ndarray,
    offsets_ms: list[float],
) -> list[dict[str, Any]]:
    old_records: list[Any] = []

    if old_sidecar is not None:
        raw_records = old_sidecar.get(
            "frame_records",
            []
        )

        if isinstance(
            raw_records,
            list
        ):
            old_records = (
                raw_records
            )

    records: list[
        dict[str, Any]
    ] = []

    for frame_index in range(
        len(
            replay_brightness
        )
    ):
        old_record: dict[str, Any] = {}

        if (
            frame_index <
            len(
                old_records
            ) and
            isinstance(
                old_records[
                    frame_index
                ],
                dict
            )
        ):
            old_record = dict(
                old_records[
                    frame_index
                ]
            )

        old_record[
            "frame_index"
        ] = frame_index

        old_record[
            "frame_number"
        ] = frame_index + 1

        if (
            "sequence_number"
            not in old_record
        ):
            old_record[
                "sequence_number"
            ] = None

        if (
            "timestamp_utc"
            not in old_record
        ):
            old_record[
                "timestamp_utc"
            ] = ""

        old_record[
            "offset_ms"
        ] = round(
            optional_float(
                old_record.get(
                    "offset_ms"
                )
            )
            if optional_float(
                old_record.get(
                    "offset_ms"
                )
            ) is not None
            else offsets_ms[
                frame_index
            ],
            3
        )

        old_record[
            "mean_brightness"
        ] = round(
            optional_float(
                old_record.get(
                    "mean_brightness"
                )
            )
            if optional_float(
                old_record.get(
                    "mean_brightness"
                )
            ) is not None
            else float(
                replay_brightness[
                    frame_index
                ]
            ),
            3
        )

        old_record[
            "brightness_delta_adjacent"
        ] = round(
            optional_float(
                old_record.get(
                    "brightness_delta_adjacent"
                )
            )
            if optional_float(
                old_record.get(
                    "brightness_delta_adjacent"
                )
            ) is not None
            else float(
                replay_brightness_delta[
                    frame_index
                ]
            ),
            3
        )

        records.append(
            old_record
        )

    return records


# ## Return whether a sidecar already contains the complete current schema.
def is_current_complete_sidecar(
    sidecar: dict[str, Any],
) -> bool:
    version = optional_int(
        sidecar.get(
            "sidecar_version"
        )
    )

    if (
        version is None or
        version <
        CURRENT_SIDECAR_VERSION
    ):
        return False

    results = sidecar.get(
        "sensitivity_results"
    )

    if not isinstance(
        results,
        dict
    ):
        return False

    for sensitivity in SENSITIVITY_NAMES:
        result = results.get(
            sensitivity
        )

        if not isinstance(
            result,
            dict
        ):
            return False

        if (
            "solution_category"
            not in result or
            "solution_reason"
            not in result or
            "candidate_config"
            not in result
        ):
            return False

    return True


# ## Create the searchable OldTrigger backup name for a migrated sidecar.
def backup_sidecar_path(
    sidecar_path: Path,
) -> Path:
    stem = sidecar_path.stem

    if stem.lower().startswith(
        "trigger_"
    ):
        backup_stem = (
            "OldTrigger_" +
            stem[
                len(
                    "trigger_"
                ):
            ]
        )
    else:
        backup_stem = (
            "OldTrigger_" +
            stem
        )

    return sidecar_path.with_name(
        backup_stem +
        sidecar_path.suffix
    )


# ## Choose an existing value unless an explicit CLI override was supplied.
def choose_metadata_value(
    explicit_value: Any,
    old_value: Any,
    fallback_value: Any,
) -> Any:
    if explicit_value is not None:
        return explicit_value

    if (
        old_value is not None and
        old_value != ""
    ):
        return old_value

    return fallback_value


# ## Project one bearing/range point from the camera on a spherical Earth.
def destination_point(
    latitude_degrees: float,
    longitude_degrees: float,
    bearing_degrees: float,
    distance_miles: float,
) -> tuple[float, float]:
    earth_radius_miles = (
        3958.7613
    )

    latitude_radians = math.radians(
        latitude_degrees
    )

    longitude_radians = math.radians(
        longitude_degrees
    )

    bearing_radians = math.radians(
        bearing_degrees
    )

    angular_distance = (
        distance_miles /
        earth_radius_miles
    )

    destination_latitude = math.asin(
        (
            math.sin(
                latitude_radians
            ) *
            math.cos(
                angular_distance
            )
        ) +
        (
            math.cos(
                latitude_radians
            ) *
            math.sin(
                angular_distance
            ) *
            math.cos(
                bearing_radians
            )
        )
    )

    destination_longitude = (
        longitude_radians +
        math.atan2(
            (
                math.sin(
                    bearing_radians
                ) *
                math.sin(
                    angular_distance
                ) *
                math.cos(
                    latitude_radians
                )
            ),
            (
                math.cos(
                    angular_distance
                ) -
                (
                    math.sin(
                        latitude_radians
                    ) *
                    math.sin(
                        destination_latitude
                    )
                )
            ),
        )
    )

    normalized_longitude = (
        (
            math.degrees(
                destination_longitude
            ) +
            540.0
        ) %
        360.0
    ) - 180.0

    return (
        math.degrees(
            destination_latitude
        ),
        normalized_longitude,
    )


# ## Return whether a compass bearing lies inside a clockwise sector.
def bearing_in_sector(
    bearing_degrees: float,
    left_degrees: float,
    right_degrees: float,
) -> bool:
    bearing = (
        bearing_degrees %
        360.0
    )

    left = (
        left_degrees %
        360.0
    )

    right = (
        right_degrees %
        360.0
    )

    if left <= right:
        return (
            left <=
            bearing <=
            right
        )

    return (
        bearing >= left or
        bearing <= right
    )


# ## Calculate the conservative geographic Search Bounding Box.
def build_search_bounding_box(
    latitude_degrees: float,
    longitude_degrees: float,
    bearing_degrees: float,
    hfov_degrees: float,
    minimum_range_miles: float,
    maximum_range_miles: float,
) -> dict[str, float]:
    minimum_range = max(
        0.0,
        minimum_range_miles
    )

    maximum_range = max(
        minimum_range,
        maximum_range_miles
    )

    half_fov = max(
        0.0,
        min(
            180.0,
            hfov_degrees /
            2.0
        )
    )

    left_bearing = (
        bearing_degrees -
        half_fov
    ) % 360.0

    right_bearing = (
        bearing_degrees +
        half_fov
    ) % 360.0

    bearings = [
        left_bearing,
        bearing_degrees %
        360.0,
        right_bearing,
    ]

    for cardinal_bearing in (
        0.0,
        90.0,
        180.0,
        270.0,
    ):
        if bearing_in_sector(
            cardinal_bearing,
            left_bearing,
            right_bearing,
        ):
            bearings.append(
                cardinal_bearing
            )

    points: list[
        tuple[
            float,
            float
        ]
    ] = []

    for range_miles in (
        minimum_range,
        maximum_range,
    ):
        for search_bearing in bearings:
            points.append(
                destination_point(
                    latitude_degrees,
                    longitude_degrees,
                    search_bearing,
                    range_miles,
                )
            )

    latitudes = [
        point[0]
        for point in points
    ]

    longitudes = [
        point[1]
        for point in points
    ]

    return {
        "minimum_range_miles":
            minimum_range,

        "maximum_range_miles":
            maximum_range,

        "min_latitude_degrees":
            round(
                min(
                    latitudes
                ),
                7
            ),

        "max_latitude_degrees":
            round(
                max(
                    latitudes
                ),
                7
            ),

        "min_longitude_degrees":
            round(
                min(
                    longitudes
                ),
                7
            ),

        "max_longitude_degrees":
            round(
                max(
                    longitudes
                ),
                7
            ),
    }


# ## Build v2 sidecar data from the MP4 plus any preserved historical sidecar.
def build_current_sidecar(
    video_path: Path,
    old_sidecar: dict[str, Any] | None,
    arguments: argparse.Namespace,
) -> dict[str, Any]:
    print(
        f"      analyzing {video_path.name}"
    )

    (
        replay_brightness,
        replay_brightness_delta,
        positive_delta_histograms,
    ) = analyze_clip(
        video_path
    )

    frame_info = read_frame_info(
        video_path
    )

    (
        nominal_fps,
        frame_width_pixels,
        frame_height_pixels,
    ) = read_video_geometry(
        video_path
    )

    frame_count = len(
        replay_brightness
    )

    offsets_ms = build_offsets_ms(
        frame_info,
        frame_count,
        nominal_fps,
    )

    (
        solution_brightness,
        solution_brightness_delta,
    ) = build_preserved_pi_metrics(
        old_sidecar,
        replay_brightness,
        replay_brightness_delta,
    )

    sensitivity_results = (
        build_sensitivity_results(
            replay_brightness,
            replay_brightness_delta,
            positive_delta_histograms,
            solution_brightness,
            solution_brightness_delta,
            offsets_ms,
        )
    )

    frame_records = (
        build_frame_records(
            old_sidecar,
            replay_brightness,
            replay_brightness_delta,
            offsets_ms,
        )
    )

    application = {}

    if (
        old_sidecar is not None and
        isinstance(
            old_sidecar.get(
                "application"
            ),
            dict
        )
    ):
        application.update(
            old_sidecar[
                "application"
            ]
        )

    application.setdefault(
        "name",
        "Pi Camera Capture"
    )

    application.setdefault(
        "version",
        sidecar_value(
            old_sidecar,
            "application",
            "version",
            "application_version",
            "",
        )
    )

    application.setdefault(
        "start_utc",
        sidecar_value(
            old_sidecar,
            "application",
            "start_utc",
            "application_start_utc",
            "",
        )
    )

    old_camera = {}

    if (
        old_sidecar is not None and
        isinstance(
            old_sidecar.get(
                "camera"
            ),
            dict
        )
    ):
        old_camera.update(
            old_sidecar[
                "camera"
            ]
        )

    site_name = choose_metadata_value(
        arguments.site_name,
        old_camera.get(
            "site_name",
            old_sidecar.get(
                "site_name"
            )
            if old_sidecar is not None
            else None
        ),
        DEFAULT_SITE_NAME,
    )

    latitude = optional_float(
        choose_metadata_value(
            arguments.latitude,
            old_camera.get(
                "latitude_degrees",
                old_sidecar.get(
                    "camera_latitude_degrees"
                )
                if old_sidecar is not None
                else None
            ),
            None,
        )
    )

    longitude = optional_float(
        choose_metadata_value(
            arguments.longitude,
            old_camera.get(
                "longitude_degrees",
                old_sidecar.get(
                    "camera_longitude_degrees"
                )
                if old_sidecar is not None
                else None
            ),
            None,
        )
    )

    bearing = optional_float(
        choose_metadata_value(
            arguments.bearing,
            old_camera.get(
                "bearing_degrees",
                old_sidecar.get(
                    "camera_bearing_degrees"
                )
                if old_sidecar is not None
                else None
            ),
            None,
        )
    )

    hfov = optional_float(
        choose_metadata_value(
            arguments.hfov,
            old_camera.get(
                "hfov_degrees",
                old_sidecar.get(
                    "camera_hfov_degrees"
                )
                if old_sidecar is not None
                else None
            ),
            None,
        )
    )

    vfov = optional_float(
        choose_metadata_value(
            arguments.vfov,
            old_camera.get(
                "vfov_degrees",
                old_sidecar.get(
                    "camera_vfov_degrees"
                )
                if old_sidecar is not None
                else None
            ),
            None,
        )
    )

    camera = dict(
        old_camera
    )

    camera[
        "site_name"
    ] = site_name

    camera.setdefault(
        "name",
        ""
    )

    camera.setdefault(
        "type",
        ""
    )

    camera.setdefault(
        "input_format",
        ""
    )

    camera[
        "frame_width_pixels"
    ] = (
        optional_int(
            old_camera.get(
                "frame_width_pixels"
            )
        ) or
        frame_width_pixels
    )

    camera[
        "frame_height_pixels"
    ] = (
        optional_int(
            old_camera.get(
                "frame_height_pixels"
            )
        ) or
        frame_height_pixels
    )

    camera[
        "frame_rate_fps"
    ] = (
        optional_float(
            old_camera.get(
                "frame_rate_fps"
            )
        ) or
        nominal_fps
    )

    camera[
        "latitude_degrees"
    ] = latitude

    camera[
        "longitude_degrees"
    ] = longitude

    camera[
        "bearing_degrees"
    ] = bearing

    camera[
        "hfov_degrees"
    ] = hfov

    camera[
        "vfov_degrees"
    ] = vfov

    search_bounding_box = None

    old_bounds = None

    if old_sidecar is not None:
        if isinstance(
            old_sidecar.get(
                "search_bounding_box"
            ),
            dict
        ):
            old_bounds = old_sidecar.get(
                "search_bounding_box"
            )
        elif isinstance(
            old_camera.get(
                "search_bounding_box"
            ),
            dict
        ):
            old_bounds = old_camera.get(
                "search_bounding_box"
            )

    geometry_overridden = any(
        value is not None
        for value in (
            arguments.latitude,
            arguments.longitude,
            arguments.bearing,
            arguments.hfov,
        )
    )

    if (
        old_bounds is not None and
        not geometry_overridden and
        arguments.minimum_range is None and
        arguments.maximum_range is None
    ):
        search_bounding_box = dict(
            old_bounds
        )
    elif all(
        value is not None
        for value in (
            latitude,
            longitude,
            bearing,
            hfov,
        )
    ):
        search_bounding_box = (
            build_search_bounding_box(
                latitude,
                longitude,
                bearing,
                hfov,
                (
                    arguments.minimum_range
                    if arguments.minimum_range is not None
                    else DEFAULT_MINIMUM_RANGE_MILES
                ),
                (
                    arguments.maximum_range
                    if arguments.maximum_range is not None
                    else DEFAULT_MAXIMUM_RANGE_MILES
                ),
            )
        )

    camera[
        "search_bounding_box"
    ] = search_bounding_box

    capture = {}

    if (
        old_sidecar is not None and
        isinstance(
            old_sidecar.get(
                "capture"
            ),
            dict
        )
    ):
        capture.update(
            old_sidecar[
                "capture"
            ]
        )

    capture.setdefault(
        "saved_utc",
        sidecar_value(
            old_sidecar,
            "capture",
            "saved_utc",
            "saved_utc",
            saved_utc_from_filename(
                video_path
            ),
        )
    )

    capture.setdefault(
        "start_utc",
        sidecar_value(
            old_sidecar,
            "capture",
            "start_utc",
            "capture_start_utc",
            "",
        )
    )

    capture.setdefault(
        "end_utc",
        sidecar_value(
            old_sidecar,
            "capture",
            "end_utc",
            "capture_end_utc",
            "",
        )
    )

    capture[
        "duration_ms"
    ] = (
        optional_float(
            sidecar_value(
                old_sidecar,
                "capture",
                "duration_ms",
                "capture_duration_ms",
                None,
            )
        )
        if old_sidecar is not None
        else None
    )

    if capture[
        "duration_ms"
    ] is None:
        capture[
            "duration_ms"
        ] = (
            round(
                (
                    offsets_ms[-1] -
                    offsets_ms[0]
                ),
                3
            )
            if frame_count > 1
            else 0.0
        )

    capture[
        "frame_count"
    ] = frame_count

    candidate = {}

    if (
        old_sidecar is not None and
        isinstance(
            old_sidecar.get(
                "candidate"
            ),
            dict
        )
    ):
        candidate.update(
            old_sidecar[
                "candidate"
            ]
        )

    # Preserve the actual historical Pi trigger when old metadata has it.
    for key, legacy_key, default in (
        (
            "trigger_type",
            "trigger_type",
            "unknown",
        ),
        (
            "trigger_display",
            "trigger_display",
            "--",
        ),
        (
            "trigger_reason",
            "trigger_reason",
            "",
        ),
        (
            "trigger_utc",
            "trigger_utc",
            "",
        ),
        (
            "trigger_sequence_number",
            "trigger_sequence_number",
            None,
        ),
        (
            "trigger_frame_index",
            "trigger_frame_index",
            None,
        ),
        (
            "trigger_offset_ms",
            "trigger_offset_ms",
            None,
        ),
        (
            "config",
            "candidate_config",
            {},
        ),
    ):
        if key not in candidate:
            candidate[
                key
            ] = sidecar_value(
                old_sidecar,
                "candidate",
                key,
                legacy_key,
                default,
            )

    result: dict[
        str,
        Any
    ] = {}

    # Preserve unknown top-level fields from the historical sidecar.
    if old_sidecar is not None:
        result.update(
            old_sidecar
        )

    result[
        "sidecar_version"
    ] = CURRENT_SIDECAR_VERSION

    result[
        "application"
    ] = application

    result[
        "camera"
    ] = camera

    result[
        "search_bounding_box"
    ] = search_bounding_box

    result[
        "capture"
    ] = capture

    result[
        "candidate"
    ] = candidate

    result[
        "sensitivity_results"
    ] = sensitivity_results

    result[
        "frame_records"
    ] = frame_records

    # Legacy helper retained because some existing consumers use it.
    result[
        "frame_count"
    ] = frame_count

    if old_sidecar is None:
        result[
            "reconstruction"
        ] = {
            "source":
                "reconstructed_from_video",

            "source_video":
                video_path.name,

            "rebuilt_utc":
                now_utc_text(),

            "tool":
                TOOL_NAME,

            "note":
                (
                    "No original sidecar was available. Values that cannot "
                    "be recovered from the encoded MP4 remain blank or null."
                ),
        }
    else:
        result[
            "migration"
        ] = {
            "source_sidecar_version":
                optional_int(
                    old_sidecar.get(
                        "sidecar_version"
                    )
                ),

            "migrated_utc":
                now_utc_text(),

            "tool":
                TOOL_NAME,
        }

    return result


# ## Validate enough of a newly built sidecar to avoid replacing good JSON with junk.
def validate_built_sidecar(
    sidecar: dict[str, Any],
) -> None:
    if (
        optional_int(
            sidecar.get(
                "sidecar_version"
            )
        ) !=
        CURRENT_SIDECAR_VERSION
    ):
        raise RuntimeError(
            "Built sidecar has wrong version"
        )

    records = sidecar.get(
        "frame_records"
    )

    if (
        not isinstance(
            records,
            list
        ) or
        not records
    ):
        raise RuntimeError(
            "Built sidecar contains no frame records"
        )

    results = sidecar.get(
        "sensitivity_results"
    )

    if not isinstance(
        results,
        dict
    ):
        raise RuntimeError(
            "Built sidecar contains no sensitivity results"
        )

    for sensitivity in SENSITIVITY_NAMES:
        if not isinstance(
            results.get(
                sensitivity
            ),
            dict
        ):
            raise RuntimeError(
                f"Built sidecar is missing {sensitivity} result"
            )


# ## Atomically write a missing sidecar.
def write_new_sidecar(
    sidecar_path: Path,
    sidecar: dict[str, Any],
) -> None:
    temporary_path = (
        sidecar_path.with_suffix(
            ".json.tmp"
        )
    )

    temporary_path.write_text(
        json.dumps(
            sidecar,
            indent=4,
        ) +
        "\n",
        encoding="utf-8",
    )

    # Verify the file we are about to install is readable JSON.
    read_sidecar(
        temporary_path
    )

    temporary_path.replace(
        sidecar_path
    )


# ## Safely migrate one old sidecar, preserving the original as OldTrigger....
def install_migrated_sidecar(
    sidecar_path: Path,
    backup_path: Path,
    sidecar: dict[str, Any],
) -> None:
    if backup_path.exists():
        raise RuntimeError(
            f"Backup already exists: {backup_path.name}"
        )

    temporary_path = (
        sidecar_path.with_suffix(
            ".json.tmp"
        )
    )

    temporary_path.write_text(
        json.dumps(
            sidecar,
            indent=4,
        ) +
        "\n",
        encoding="utf-8",
    )

    read_sidecar(
        temporary_path
    )

    sidecar_path.replace(
        backup_path
    )

    try:
        temporary_path.replace(
            sidecar_path
        )
    except Exception:
        # Restore the original normal-name sidecar if final installation fails.
        if (
            backup_path.exists() and
            not sidecar_path.exists()
        ):
            backup_path.replace(
                sidecar_path
            )

        raise


# ## Determine and execute the action for one MP4.
def process_file(
    video_path: Path,
    arguments: argparse.Namespace,
) -> tuple[str, bool]:
    if not video_path.is_file():
        raise RuntimeError(
            f"File not found: {video_path}"
        )

    if video_path.suffix.lower() != ".mp4":
        raise RuntimeError(
            f"Target file must be an MP4: {video_path}"
        )

    sidecar_path = (
        video_path.with_suffix(
            ".json"
        )
    )

    old_sidecar = None
    action = "REBUILD"

    if sidecar_path.exists():
        old_sidecar = read_sidecar(
            sidecar_path
        )

        if is_current_complete_sidecar(
            old_sidecar
        ):
            print(
                f"CURRENT {video_path}"
            )

            return (
                "current",
                True,
            )

        action = "MIGRATE"

    if action == "MIGRATE":
        backup_path = backup_sidecar_path(
            sidecar_path
        )

        if backup_path.exists():
            print(
                f"FAIL    {video_path} "
                f"(backup already exists: {backup_path.name})"
            )

            return (
                "failed",
                False,
            )

        old_version = optional_int(
            old_sidecar.get(
                "sidecar_version"
            )
            if old_sidecar is not None
            else None
        )

        version_text = (
            str(
                old_version
            )
            if old_version is not None
            else "unknown"
        )

        if arguments.dry_run:
            print(
                f"WOULD MIGRATE v{version_text} -> "
                f"v{CURRENT_SIDECAR_VERSION}  {video_path}"
            )
            print(
                f"              backup -> {backup_path.name}"
            )

            return (
                "migrated",
                True,
            )

        print(
            f"MIGRATE v{version_text} -> "
            f"v{CURRENT_SIDECAR_VERSION}  {video_path}"
        )

        try:
            built_sidecar = (
                build_current_sidecar(
                    video_path,
                    old_sidecar,
                    arguments,
                )
            )

            built_sidecar[
                "migration"
            ][
                "backup_sidecar"
            ] = backup_path.name

            validate_built_sidecar(
                built_sidecar
            )

            install_migrated_sidecar(
                sidecar_path,
                backup_path,
                built_sidecar,
            )

            print(
                f"        backup -> {backup_path.name}"
            )

            return (
                "migrated",
                True,
            )

        except Exception as error:
            print(
                f"FAIL    {video_path}: {error}"
            )

            return (
                "failed",
                False,
            )

    if arguments.dry_run:
        print(
            f"WOULD REBUILD v{CURRENT_SIDECAR_VERSION}  {video_path}"
        )

        return (
            "rebuilt",
            True,
        )

    print(
        f"REBUILD v{CURRENT_SIDECAR_VERSION}  {video_path}"
    )

    try:
        built_sidecar = (
            build_current_sidecar(
                video_path,
                None,
                arguments,
            )
        )

        validate_built_sidecar(
            built_sidecar
        )

        write_new_sidecar(
            sidecar_path,
            built_sidecar,
        )

        print(
            f"        -> {sidecar_path.name}"
        )

        return (
            "rebuilt",
            True,
        )

    except Exception as error:
        print(
            f"FAIL    {video_path}: {error}"
        )

        return (
            "failed",
            False,
        )


# ## Process one directory, optionally including its subdirectories.
def process_folder(
    folder: Path,
    arguments: argparse.Namespace,
) -> dict[str, int]:
    if not folder.is_dir():
        raise RuntimeError(
            f"Folder not found: {folder}"
        )

    pattern = (
        "**/*.mp4"
        if arguments.recursive
        else "*.mp4"
    )

    video_files = sorted(
        folder.glob(
            pattern
        )
    )

    counts = {
        "rebuilt": 0,
        "migrated": 0,
        "current": 0,
        "failed": 0,
    }

    for video_path in video_files:
        status, _ = process_file(
            video_path,
            arguments,
        )

        counts[
            status
        ] += 1

    return counts


# ## Build command-line parser shared by Windows, Linux, and Pi.
def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Rebuild missing sidecars and migrate older sidecars "
            f"to version {CURRENT_SIDECAR_VERSION}."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  RebuildSidecars\n"
            "  RebuildSidecars trigger_20260821T120000Z.mp4\n"
            "  RebuildSidecars C:\\\\Lightning\\\\true_flashes\n"
            "  RebuildSidecars C:\\\\Lightning --recursive --dry-run\n"
            "  RebuildSidecars /home/pi/captures --recursive\n"
            "\n"
            "Optional site/camera values are used only when missing from an "
            "older sidecar, except explicitly supplied values always override."
        ),
    )

    parser.add_argument(
        "target",
        nargs="?",
        type=Path,
        default=Path("."),
        help=(
            "MP4 file or folder to process; defaults to current directory"
        ),
    )

    parser.add_argument(
        "--recursive",
        action="store_true",
        help=(
            "When target is a folder, also process MP4s in subfolders"
        ),
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "Report rebuild/migration actions without changing any files"
        ),
    )

    parser.add_argument(
        "--site-name",
        default=None,
        help=(
            f"Site name override/fallback; missing metadata defaults to "
            f"{DEFAULT_SITE_NAME}"
        ),
    )

    parser.add_argument(
        "--latitude",
        type=float,
        default=None,
        help="Camera latitude override in degrees",
    )

    parser.add_argument(
        "--longitude",
        type=float,
        default=None,
        help="Camera longitude override in degrees",
    )

    parser.add_argument(
        "--bearing",
        type=float,
        default=None,
        help="Camera bearing override in degrees",
    )

    parser.add_argument(
        "--hfov",
        type=float,
        default=None,
        help="Camera horizontal field of view override in degrees",
    )

    parser.add_argument(
        "--vfov",
        type=float,
        default=None,
        help="Camera vertical field of view override in degrees",
    )

    parser.add_argument(
        "--minimum-range",
        type=float,
        default=None,
        help=(
            "Search Bounding Box minimum range in miles; "
            f"default {DEFAULT_MINIMUM_RANGE_MILES}"
        ),
    )

    parser.add_argument(
        "--maximum-range",
        type=float,
        default=None,
        help=(
            "Search Bounding Box maximum range in miles; "
            f"default {DEFAULT_MAXIMUM_RANGE_MILES}"
        ),
    )

    return parser


# ## Validate optional camera geometry supplied on the command line.
def validate_arguments(
    parser: argparse.ArgumentParser,
    arguments: argparse.Namespace,
) -> None:
    if (
        arguments.latitude is not None and
        not -90.0 <= arguments.latitude <= 90.0
    ):
        parser.error(
            "--latitude must be between -90 and 90"
        )

    if (
        arguments.longitude is not None and
        not -180.0 <= arguments.longitude <= 180.0
    ):
        parser.error(
            "--longitude must be between -180 and 180"
        )

    if (
        arguments.bearing is not None and
        not 0.0 <= arguments.bearing < 360.0
    ):
        parser.error(
            "--bearing must be at least 0 and less than 360"
        )

    if (
        arguments.hfov is not None and
        not 0.0 <= arguments.hfov <= 360.0
    ):
        parser.error(
            "--hfov must be between 0 and 360"
        )

    if (
        arguments.vfov is not None and
        not 0.0 <= arguments.vfov <= 180.0
    ):
        parser.error(
            "--vfov must be between 0 and 180"
        )

    if (
        arguments.minimum_range is not None and
        arguments.minimum_range < 0.0
    ):
        parser.error(
            "--minimum-range must be >= 0"
        )

    if (
        arguments.maximum_range is not None and
        arguments.maximum_range < 0.0
    ):
        parser.error(
            "--maximum-range must be >= 0"
        )

    minimum_range = (
        arguments.minimum_range
        if arguments.minimum_range is not None
        else DEFAULT_MINIMUM_RANGE_MILES
    )

    maximum_range = (
        arguments.maximum_range
        if arguments.maximum_range is not None
        else DEFAULT_MAXIMUM_RANGE_MILES
    )

    if maximum_range < minimum_range:
        parser.error(
            "--maximum-range must be >= --minimum-range"
        )


# ## Entry point: process a file or batch, then print a concise summary.
def main() -> int:
    parser = (
        build_argument_parser()
    )

    arguments = (
        parser.parse_args()
    )

    validate_arguments(
        parser,
        arguments,
    )

    try:
        target = arguments.target

        if target.is_file():
            if arguments.recursive:
                parser.error(
                    "--recursive can only be used with a folder"
                )

            counts = {
                "rebuilt": 0,
                "migrated": 0,
                "current": 0,
                "failed": 0,
            }

            status, _ = process_file(
                target,
                arguments,
            )

            counts[
                status
            ] += 1

        elif target.is_dir():
            counts = process_folder(
                target,
                arguments,
            )

        else:
            raise RuntimeError(
                f"Target not found: {target}"
            )

        print()
        print(
            "Dry run summary:"
            if arguments.dry_run
            else "Summary:"
        )

        print(
            f"  Rebuilt:  {counts['rebuilt']}"
        )

        print(
            f"  Migrated: {counts['migrated']}"
        )

        print(
            f"  Current:  {counts['current']}"
        )

        print(
            f"  Failed:   {counts['failed']}"
        )

        return (
            0
            if counts[
                "failed"
            ] == 0
            else 1
        )

    except (
        OSError,
        RuntimeError,
    ) as error:
        print(
            f"Sidecar maintenance failed: {error}"
        )

        return 1


if __name__ == "__main__":
    sys.exit(
        main()
    )
