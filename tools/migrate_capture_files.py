"""
@file migrate_capture_files.py

@brief Strict migration of complete Pi Camera Capture sidecars to V7.

This tool is deliberately conservative.  It migrates metadata only and never
decodes MP4 files or reconstructs missing metadata.

A source sidecar is accepted only when it is a complete Pi Camera Capture
sidecar.  Analysis-era/reconstructed JSON files and incomplete sidecars are
REJECTED rather than being stamped as V7.

Required source sections:
    application
    camera
    capture
    candidate
    sensitivity_results
    frame_records

For V5 and earlier complete sidecars:
* Historical CG/IC/LCC classification means human-confirmed True Flash:
      capture.verified = True
      capture.classification = "TF"
      capture.type = CG/IC/LCC
      filename prefix = flash_

* Existing historical category folders created by filter_solutions are
  authoritative workflow metadata:
      bright_noise_anomalies      -> verified NA
      steady_state_anomalies      -> verified SSA
      stair_step_decay_anomalies  -> verified STA
      frame_dropout_anomalies     -> verified FDA
      not_candidates              -> verified NAC

* A capture not in one of those folders is not auto-verified from its H-M-L
  replay signature.  The signature is preserved and the capture remains
  unverified unless it was already human-classified CG/IC/LCC.

For an already-current V7 sidecar:
* The complete V7 structure is validated.
* Existing verified final adjudication is preserved.
* An unverified recognized anomaly may be repaired to verified using the
  stored active-sensitivity SolutionFilter result.
* Camera/application/candidate/sensitivity/frame metadata is preserved.

The migration NEVER invents camera/site/location metadata.

With -cf/--copy-files OUTPUT_FOLDER:
* originals are untouched;
* migrated MP4/JSON pairs are written flat into OUTPUT_FOLDER;
* existing destination filenames are treated as duplicates and skipped.

Examples:
    python tools/migrate_capture_files.py C:\\Lightning --recursive --dry-run
    python tools/migrate_capture_files.py C:\\Lightning --recursive -cf C:\\capturesV7
"""


from __future__ import annotations

import argparse
import json
import math
import shutil
from pathlib import Path
import sys
from typing import Any


CURRENT_SIDECAR_VERSION = 7
TOOL_NAME = "MigrateCaptures"

SENSITIVITY_NAMES = (
    "high",
    "medium",
    "low",
)

LIGHTNING_TYPES = (
    "UK",
    "CG",
    "IC",
    "LCC",
)

FINAL_CLASSIFICATION_CODES = (
    "TF",
    "NA",
    "STA",
    "SSA",
    "FDA",
    "NAC",
    "UFA",
)

# UNK is deliberately not a final verified classification. It is only a token
# used in an unverified High-Medium-Low signature when migration cannot recover
# one of the three stored algorithm results.
SIGNATURE_UNKNOWN_CODE = "UNK"

SOLUTION_CATEGORY_TO_CODE = {
    "TRUE_FLASH": "TF",

    "BRIGHT_NOISE": "NA",
    "BRIGHT_NOISE_ANOMALY": "NA",
    "NOISE_ANOMALY": "NA",

    "STAIR_STEP_DECAY": "STA",
    "STAIRSTEP_ANOMALY": "STA",
    "STAIR_STEP_ANOMALY": "STA",
    "SST": "STA",

    "STEADY_STATE_CHANGE": "SSA",
    "STEADY_STATE_ANOMALY": "SSA",

    "FRAME_DROPOUT": "FDA",
    "FRAME_DROPOUT_ANOMALY": "FDA",

    "FAILED_CANDIDATE": "NAC",
    "NO_CANDIDATE": "NAC",
    "NOT_A_CANDIDATE": "NAC",

    "UNIDENTIFIED_FLYING_ANOMALY": "UFA",
}


def read_sidecar(sidecar_path: Path) -> dict[str, Any]:
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

    if not isinstance(data, dict):
        raise RuntimeError(
            "Sidecar JSON must contain an object"
        )

    return data


def optional_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def normalized_solution_category(value: Any) -> str:
    return str(
        value or ""
    ).strip().upper().replace(
        "-",
        "_",
    ).replace(
        " ",
        "_",
    )


def solution_category_code(value: Any) -> str:
    category = normalized_solution_category(
        value
    )

    return SOLUTION_CATEGORY_TO_CODE.get(
        category,
        SIGNATURE_UNKNOWN_CODE,
    )


def build_hml_classification(
    sidecar: dict[str, Any],
) -> str:
    sensitivity_results = sidecar.get(
        "sensitivity_results"
    )

    if not isinstance(
        sensitivity_results,
        dict,
    ):
        return "-".join(
            SIGNATURE_UNKNOWN_CODE
            for _ in SENSITIVITY_NAMES
        )

    codes: list[str] = []

    for sensitivity in SENSITIVITY_NAMES:
        result = sensitivity_results.get(
            sensitivity
        )

        if not isinstance(
            result,
            dict,
        ):
            codes.append(
                SIGNATURE_UNKNOWN_CODE
            )
            continue

        codes.append(
            solution_category_code(
                result.get(
                    "solution_category"
                )
            )
        )

    return "-".join(
        codes
    )


REQUIRED_SOURCE_SECTIONS = (
    "application",
    "camera",
    "capture",
    "candidate",
    "sensitivity_results",
    "frame_records",
)

ANOMALY_CLASSIFICATION_CODES = {
    "NA",
    "STA",
    "SSA",
    "FDA",
}


SOURCE_FOLDER_CLASSIFICATION = {
    "bright_noise_anomalies": "NA",
    "steady_state_anomalies": "SSA",
    "stair_step_decay_anomalies": "STA",
    "frame_dropout_anomalies": "FDA",
    "not_candidates": "NAC",
}


V7_FRAME_RECORD_FIELDS = (
    "frame_index",
    "timestamp_utc",
    "offset_ms",
    "mean_brightness",
    "brightness_delta_adjacent",
)


def compact_frame_records(
    records: list[Any],
) -> list[dict[str, Any]]:
    compact: list[dict[str, Any]] = []

    for list_index, record in enumerate(records):
        if not isinstance(record, dict):
            raise RuntimeError(
                f"Invalid frame record at index {list_index}"
            )

        output: dict[str, Any] = {}

        for key in V7_FRAME_RECORD_FIELDS:
            if key == "frame_index":
                value = record.get(key, list_index)
            else:
                if key not in record:
                    raise RuntimeError(
                        f"Frame record {list_index} is missing {key}"
                    )
                value = record[key]

            output[key] = value

        compact.append(output)

    return compact


def capture_brightness_summary(
    records: list[Any],
) -> tuple[float, float]:
    brightness_values: list[float] = []
    delta_values: list[float] = []

    for record in records:
        if not isinstance(record, dict):
            continue

        try:
            brightness = float(record["mean_brightness"])
            delta = float(record["brightness_delta_adjacent"])
        except (KeyError, TypeError, ValueError):
            continue

        if math.isfinite(brightness):
            brightness_values.append(brightness)
        if math.isfinite(delta):
            delta_values.append(delta)

    if not brightness_values:
        raise RuntimeError(
            "frame_records contain no valid mean_brightness values"
        )
    if not delta_values:
        raise RuntimeError(
            "frame_records contain no valid brightness_delta_adjacent values"
        )

    return (
        round(max(0.0, max(delta_values)), 1),
        round(sum(brightness_values) / len(brightness_values), 1),
    )


def compact_search_bounding_box(
    camera: dict[str, Any],
) -> dict[str, Any]:
    output = dict(camera)
    box = camera.get("search_bounding_box")

    if not isinstance(box, dict):
        return output

    if all(key in box for key in ("range", "lat", "lon")):
        output["search_bounding_box"] = {
            "range": list(box["range"]),
            "lat": list(box["lat"]),
            "lon": list(box["lon"]),
        }
        return output

    required = (
        "minimum_range_miles",
        "maximum_range_miles",
        "min_latitude_degrees",
        "max_latitude_degrees",
        "min_longitude_degrees",
        "max_longitude_degrees",
    )

    if not all(key in box for key in required):
        raise RuntimeError(
            "camera.search_bounding_box is incomplete"
        )

    output["search_bounding_box"] = {
        "range": [
            box["minimum_range_miles"],
            box["maximum_range_miles"],
        ],
        "lat": [
            box["min_latitude_degrees"],
            box["max_latitude_degrees"],
        ],
        "lon": [
            box["min_longitude_degrees"],
            box["max_longitude_degrees"],
        ],
    }

    return output




def require_dict_section(
    sidecar: dict[str, Any],
    name: str,
) -> dict[str, Any]:
    value = sidecar.get(
        name
    )

    if not isinstance(
        value,
        dict,
    ):
        raise RuntimeError(
            f"Source sidecar is incomplete: '{name}' must be an object"
        )

    return value


def validate_source_sidecar(
    sidecar: dict[str, Any],
) -> int:
    """Reject incomplete/analysis-era JSON before any V7 metadata is built."""
    if "analysis_version" in sidecar:
        raise RuntimeError(
            "Source JSON is an analysis-era/incomplete sidecar; "
            "refusing to manufacture V7 metadata from it"
        )

    version = optional_int(
        sidecar.get(
            "sidecar_version"
        )
    )

    if version is None:
        raise RuntimeError(
            "Source sidecar has no valid sidecar_version"
        )

    if version > CURRENT_SIDECAR_VERSION:
        raise RuntimeError(
            f"Source sidecar version {version} is newer than this tool"
        )

    application = require_dict_section(
        sidecar,
        "application",
    )
    camera = require_dict_section(
        sidecar,
        "camera",
    )
    capture = require_dict_section(
        sidecar,
        "capture",
    )
    candidate = require_dict_section(
        sidecar,
        "candidate",
    )
    sensitivity_results = require_dict_section(
        sidecar,
        "sensitivity_results",
    )

    records = sidecar.get(
        "frame_records"
    )
    if not isinstance(
        records,
        list,
    ) or not records:
        raise RuntimeError(
            "Source sidecar is incomplete: 'frame_records' must be a non-empty list"
        )

    # These fields are the camera metadata that migration must preserve.  A
    # complete source camera section must contain them; values may legitimately
    # be blank/None in genuinely reconstructed historical data, but this tool
    # will never invent replacements.
    for key in (
        "site_name",
        "latitude_degrees",
        "longitude_degrees",
        "bearing_degrees",
        "hfov_degrees",
        "vfov_degrees",
    ):
        if key not in camera:
            raise RuntimeError(
                f"Source camera metadata is incomplete: missing camera.{key}"
            )

    # A complete Pi sidecar must carry all three stored SolutionFilter results.
    for sensitivity in SENSITIVITY_NAMES:
        result = sensitivity_results.get(
            sensitivity
        )
        if not isinstance(
            result,
            dict,
        ):
            raise RuntimeError(
                f"Source sidecar is incomplete: missing "
                f"sensitivity_results.{sensitivity}"
            )
        if "solution_category" not in result:
            raise RuntimeError(
                f"Source sidecar is incomplete: "
                f"sensitivity_results.{sensitivity}.solution_category missing"
            )

    # Candidate metadata itself is still required, but migration no longer
    # depends on one active sensitivity value. Historical sidecars already
    # contain all three stored SolutionFilter results.
    # Touch the dictionaries above deliberately: they are required structural
    # sections even where this migration does not rewrite their contents.
    _ = application, capture

    return version


def anomaly_classification_from_results(
    sidecar: dict[str, Any],
) -> str | None:
    """Return the first stored anomaly classification in H-M-L order.

    Historical captures store SolutionFilter results for all three sensitivity
    levels.  Any recognized anomaly means the capture does not require human
    verification.  High -> Medium -> Low provides a deterministic choice if
    historical results contain more than one anomaly category.
    """
    sensitivity_results = sidecar[
        "sensitivity_results"
    ]

    for sensitivity in SENSITIVITY_NAMES:
        result = sensitivity_results[
            sensitivity
        ]

        code = solution_category_code(
            result.get(
                "solution_category"
            )
        )

        if code in ANOMALY_CLASSIFICATION_CODES:
            return code

    return None


def all_nac_classification(
    sidecar: dict[str, Any],
) -> bool:
    """Return True only when all three stored H-M-L results are NAC."""
    sensitivity_results = sidecar[
        "sensitivity_results"
    ]

    codes = [
        solution_category_code(
            sensitivity_results[
                sensitivity
            ].get(
                "solution_category"
            )
        )
        for sensitivity in SENSITIVITY_NAMES
    ]

    return all(
        code == "NAC"
        for code in codes
    )



def valid_hml_signature(
    value: Any,
) -> bool:
    parts = str(
        value or ""
    ).strip().upper().split(
        "-"
    )

    return (
        len(parts) == 3
        and all(
            part in FINAL_CLASSIFICATION_CODES
            or part == SIGNATURE_UNKNOWN_CODE
            for part in parts
        )
    )



def classification_from_source_path(
    video_path: Path,
) -> str | None:
    """Return authoritative classification encoded by an old category folder."""
    for parent in video_path.parents:
        code = SOURCE_FOLDER_CLASSIFICATION.get(
            parent.name.strip().lower()
        )
        if code is not None:
            return code

    return None



def migrate_sidecar(
    old_sidecar: dict[str, Any],
    source_classification: str | None = None,
) -> dict[str, Any]:
    """Return a strict V7 copy without modifying the input dictionary."""
    old_version = validate_source_sidecar(
        old_sidecar
    )

    old_capture = old_sidecar[
        "capture"
    ]

    # V5 annotation lived at the top level.  V7 adjudication lives in capture.
    old_classification = str(
        old_sidecar.get(
            "classification",
            "",
        ) or ""
    ).strip().upper()

    if source_classification is not None:
        # Historical filter_solutions already adjudicated this capture by
        # placing it in a category folder.  That decision is authoritative.
        verified = True
        classification = source_classification
        lightning_type = "UK"

    elif (
        old_version <= 5
        and old_classification in LIGHTNING_TYPES[1:]
    ):
        verified = True
        classification = "TF"
        lightning_type = old_classification

    elif old_version <= 5:
        # Not previously sorted into an anomaly/reject folder and not a
        # human-classified flash: keep it pending for human review.
        verified = False
        classification = build_hml_classification(
            old_sidecar
        )
        lightning_type = "UK"

    else:
        if source_classification is not None:
            verified = True
            classification = source_classification
            lightning_type = "UK"
        else:
            verified = old_capture.get(
                "verified"
            )

            if not isinstance(
                verified,
                bool,
            ):
                raise RuntimeError(
                    "V7 capture.verified must be boolean"
                )

            raw_classification = str(
                old_capture.get(
                    "classification",
                    "",
                ) or ""
            ).strip().upper()

            raw_type = str(
                old_capture.get(
                    "type",
                    "UK",
                ) or "UK"
            ).strip().upper()

            if raw_type not in LIGHTNING_TYPES:
                raise RuntimeError(
                    f"V7 capture.type is invalid: {raw_type or '<blank>'}"
                )

            lightning_type = raw_type

            if verified:
                if raw_classification not in FINAL_CLASSIFICATION_CODES:
                    raise RuntimeError(
                        "Verified V7 sidecar has invalid final classification: "
                        f"{raw_classification or '<blank>'}"
                    )
                classification = raw_classification
            else:
                if not valid_hml_signature(
                    raw_classification
                ):
                    raise RuntimeError(
                        "Unverified V7 capture.classification must be an "
                        "H-M-L three-code signature"
                    )

                classification = raw_classification
                lightning_type = "UK"

    description = str(
        old_capture.get(
            "description",
            old_sidecar.get(
                "description",
                "",
            ),
        ) or ""
    )

    # Preserve complete source sections exactly.  Only the V7 workflow fields,
    # application version, obsolete top-level annotation fields, and migration
    # bookkeeping are changed.
    migrated: dict[str, Any] = {}

    migrated[
        "sidecar_version"
    ] = CURRENT_SIDECAR_VERSION

    application = dict(
        old_sidecar[
            "application"
        ]
    )
    application[
        "version"
    ] = "0.92"
    migrated[
        "application"
    ] = application

    migrated[
        "capture"
    ] = dict(
        old_capture
    )
    migrated[
        "capture"
    ][
        "verified"
    ] = verified
    migrated[
        "capture"
    ][
        "classification"
    ] = classification
    migrated[
        "capture"
    ][
        "type"
    ] = lightning_type
    migrated[
        "capture"
    ][
        "description"
    ] = description

    (
        max_brightness_delta,
        mean_brightness,
    ) = capture_brightness_summary(
        old_sidecar["frame_records"]
    )

    migrated["capture"]["max_brightness_delta"] = (
        max_brightness_delta
    )
    migrated["capture"]["mean_brightness"] = (
        mean_brightness
    )

    migrated["camera"] = compact_search_bounding_box(
        old_sidecar["camera"]
    )

    # Canonical V7 section order.  Keep Candidate and sensitivity replay
    # results adjacent to the camera metadata and immediately before the
    # per-frame records.  Re-running this tool on an existing V7 sidecar
    # rewrites the JSON into this order without changing sidecar_version.
    migrated["candidate"] = old_sidecar[
        "candidate"
    ]
    migrated["sensitivity_results"] = old_sidecar[
        "sensitivity_results"
    ]

    migrated["frame_records"] = compact_frame_records(
        old_sidecar["frame_records"]
    )

    for key, value in old_sidecar.items():
        if key in {
            "sidecar_version",
            "application",
            "capture",
            "camera",
            "candidate",
            "sensitivity_results",
            "frame_records",
            "verified",
            "classification",
            "type",
            "description",
            "search_bounding_box",
            "migration",
        }:
            continue

        migrated[
            key
        ] = value

    migration = old_sidecar.get(
        "migration"
    )
    if not isinstance(
        migration,
        dict,
    ):
        migration = {}

    migration = dict(
        migration
    )
    migration[
        "source_sidecar_version"
    ] = old_version
    migration[
        "tool"
    ] = TOOL_NAME

    migrated[
        "migration"
    ] = migration

    return migrated

def is_verified_true_flash(
    sidecar: dict[str, Any],
) -> bool:
    capture = sidecar.get(
        "capture"
    )

    if not isinstance(
        capture,
        dict,
    ):
        return False

    return (
        capture.get(
            "verified"
        ) is True
        and str(
            capture.get(
                "classification",
                "",
            ) or ""
        ).strip().upper() == "TF"
    )


def strip_capture_prefix(stem: str) -> str:
    lower = stem.lower()

    for prefix in (
        "trigger_",
        "capture_",
        "flash_",
    ):
        if lower.startswith(
            prefix
        ):
            return stem[
                len(prefix):
            ]

    return stem


def migrated_stem(
    source_stem: str,
    sidecar: dict[str, Any],
) -> str:
    suffix = strip_capture_prefix(
        source_stem
    )

    prefix = (
        "flash_"
        if is_verified_true_flash(
            sidecar
        )
        else "capture_"
    )

    return (
        prefix +
        suffix
    )


def validate_migrated_sidecar(
    sidecar: dict[str, Any],
    source_sidecar: dict[str, Any] | None = None,
) -> None:
    if optional_int(
        sidecar.get(
            "sidecar_version"
        )
    ) != CURRENT_SIDECAR_VERSION:
        raise RuntimeError(
            "Migrated sidecar has wrong version"
        )

    if "analysis_version" in sidecar:
        raise RuntimeError(
            "Migrated V7 sidecar must not contain analysis_version"
        )

    top_level_keys = list(
        sidecar.keys()
    )

    required_order = (
        "sidecar_version",
        "application",
        "capture",
        "camera",
        "candidate",
        "sensitivity_results",
        "frame_records",
    )

    try:
        positions = [
            top_level_keys.index(
                key
            )
            for key in required_order
        ]
    except ValueError as error:
        raise RuntimeError(
            "Migrated V7 sidecar is missing a required top-level section"
        ) from error

    if positions != sorted(
        positions
    ):
        raise RuntimeError(
            "Migrated V7 top-level sections are not in canonical order"
        )

    for section_name in REQUIRED_SOURCE_SECTIONS:
        if section_name == "frame_records":
            records = sidecar.get(
                section_name
            )
            if not isinstance(
                records,
                list,
            ) or not records:
                raise RuntimeError(
                    "Migrated sidecar has no frame_records"
                )
            continue

        if not isinstance(
            sidecar.get(
                section_name
            ),
            dict,
        ):
            raise RuntimeError(
                f"Migrated sidecar is missing {section_name}"
            )

    capture = sidecar[
        "capture"
    ]

    for index, record in enumerate(sidecar["frame_records"]):
        if not isinstance(record, dict):
            raise RuntimeError(
                f"Migrated frame record {index} is not an object"
            )

        if tuple(record.keys()) != V7_FRAME_RECORD_FIELDS:
            raise RuntimeError(
                f"Migrated frame record {index} has unexpected fields"
            )

    camera = sidecar["camera"]
    box = camera.get("search_bounding_box")

    if isinstance(box, dict):
        if set(box) != {"range", "lat", "lon"}:
            raise RuntimeError(
                "Migrated camera.search_bounding_box is not V7 compact form"
            )

    if not isinstance(
        capture.get(
            "verified"
        ),
        bool,
    ):
        raise RuntimeError(
            "Migrated capture.verified is not boolean"
        )

    lightning_type = str(
        capture.get(
            "type",
            "",
        ) or ""
    ).strip().upper()

    if lightning_type not in LIGHTNING_TYPES:
        raise RuntimeError(
            f"Migrated capture has invalid type: {lightning_type}"
        )

    classification = str(
        capture.get(
            "classification",
            "",
        ) or ""
    ).strip().upper()

    if capture[
        "verified"
    ]:
        if classification not in FINAL_CLASSIFICATION_CODES:
            raise RuntimeError(
                "Verified capture must have one final classification"
            )
    elif not valid_hml_signature(
        classification
    ):
        raise RuntimeError(
            "Unverified capture classification must be an "
            "H-M-L three-code signature"
        )

    # Prove that migration changed only the deliberate V7 compact fields.
    if source_sidecar is not None:
        expected_camera = compact_search_bounding_box(
            source_sidecar["camera"]
        )

        if sidecar["camera"] != expected_camera:
            raise RuntimeError(
                "Migration changed camera metadata outside "
                "search_bounding_box compaction"
            )

        for section_name in (
            "candidate",
            "sensitivity_results",
        ):
            if sidecar[section_name] != source_sidecar[section_name]:
                raise RuntimeError(
                    f"Migration changed preserved section: {section_name}"
                )

        expected_records = compact_frame_records(
            source_sidecar["frame_records"]
        )

        if sidecar["frame_records"] != expected_records:
            raise RuntimeError(
                "Migration produced incorrect V7 frame_records"
            )

    expected_max_delta, expected_mean_brightness = (
        capture_brightness_summary(
            sidecar["frame_records"]
        )
    )

    if capture.get("max_brightness_delta") != expected_max_delta:
        raise RuntimeError(
            "Migrated capture.max_brightness_delta is incorrect"
        )

    if capture.get("mean_brightness") != expected_mean_brightness:
        raise RuntimeError(
            "Migrated capture.mean_brightness is incorrect"
        )



def write_sidecar_temp(
    destination_json_path: Path,
    sidecar: dict[str, Any],
) -> Path:
    temporary_path = destination_json_path.with_name(
        destination_json_path.name +
        ".migration.tmp"
    )

    if temporary_path.exists():
        raise RuntimeError(
            f"Temporary migration file already exists: {temporary_path}"
        )

    temporary_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    temporary_path.write_text(
        json.dumps(
            sidecar,
            indent=4,
        ) +
        "\n",
        encoding="utf-8",
    )

    # Parse the actual staged file before it can replace anything.
    read_sidecar(
        temporary_path
    )

    return temporary_path


def install_copy(
    source_video_path: Path,
    destination_video_path: Path,
    destination_sidecar_path: Path,
    migrated_sidecar: dict[str, Any],
) -> None:
    if destination_video_path.exists():
        raise RuntimeError(
            f"Destination already exists: {destination_video_path}"
        )

    if destination_sidecar_path.exists():
        raise RuntimeError(
            f"Destination already exists: {destination_sidecar_path}"
        )

    destination_video_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    temporary_sidecar_path = write_sidecar_temp(
        destination_sidecar_path,
        migrated_sidecar,
    )

    try:
        shutil.copy2(
            source_video_path,
            destination_video_path,
        )

        temporary_sidecar_path.replace(
            destination_sidecar_path
        )

    except Exception:
        destination_video_path.unlink(
            missing_ok=True
        )
        destination_sidecar_path.unlink(
            missing_ok=True
        )
        temporary_sidecar_path.unlink(
            missing_ok=True
        )
        raise


def install_in_place(
    source_video_path: Path,
    source_sidecar_path: Path,
    destination_video_path: Path,
    destination_sidecar_path: Path,
    migrated_sidecar: dict[str, Any],
) -> None:
    rename_needed = (
        destination_video_path != source_video_path
    )

    if (
        rename_needed
        and destination_video_path.exists()
    ):
        raise RuntimeError(
            f"Destination already exists: {destination_video_path}"
        )

    if (
        destination_sidecar_path != source_sidecar_path
        and destination_sidecar_path.exists()
    ):
        raise RuntimeError(
            f"Destination already exists: {destination_sidecar_path}"
        )

    temporary_sidecar_path = write_sidecar_temp(
        destination_sidecar_path,
        migrated_sidecar,
    )

    # If the name does not change, JSON replacement is individually atomic.
    if not rename_needed:
        try:
            temporary_sidecar_path.replace(
                source_sidecar_path
            )
        except Exception:
            temporary_sidecar_path.unlink(
                missing_ok=True
            )
            raise
        return

    # For a pair rename, keep the old JSON only as a transient rollback file.
    # It is removed immediately after the new pair is installed successfully.
    rollback_sidecar_path = source_sidecar_path.with_name(
        source_sidecar_path.name +
        ".migration.rollback.tmp"
    )

    if rollback_sidecar_path.exists():
        temporary_sidecar_path.unlink(
            missing_ok=True
        )
        raise RuntimeError(
            f"Rollback migration file already exists: {rollback_sidecar_path}"
        )

    video_renamed = False
    sidecar_staged_for_rollback = False

    try:
        source_sidecar_path.replace(
            rollback_sidecar_path
        )
        sidecar_staged_for_rollback = True

        source_video_path.replace(
            destination_video_path
        )
        video_renamed = True

        temporary_sidecar_path.replace(
            destination_sidecar_path
        )

        rollback_sidecar_path.unlink()

    except Exception:
        # Remove a partially installed new sidecar before restoring the old one.
        if (
            destination_sidecar_path.exists()
            and destination_sidecar_path != source_sidecar_path
        ):
            destination_sidecar_path.unlink(
                missing_ok=True
            )

        temporary_sidecar_path.unlink(
            missing_ok=True
        )

        if video_renamed and destination_video_path.exists():
            destination_video_path.replace(
                source_video_path
            )

        if (
            sidecar_staged_for_rollback
            and rollback_sidecar_path.exists()
        ):
            rollback_sidecar_path.replace(
                source_sidecar_path
            )

        raise


def process_capture(
    video_path: Path,
    arguments: argparse.Namespace,
    target_root: Path,
    copy_root: Path | None,
) -> str:
    sidecar_path = video_path.with_suffix(
        ".json"
    )

    if not sidecar_path.is_file():
        raise RuntimeError(
            f"Matching JSON sidecar not found: {sidecar_path.name}"
        )

    old_sidecar = read_sidecar(
        sidecar_path
    )

    source_classification = classification_from_source_path(
        video_path
    )

    migrated_sidecar = migrate_sidecar(
        old_sidecar,
        source_classification=source_classification,
    )

    validate_migrated_sidecar(
        migrated_sidecar,
        old_sidecar,
    )

    destination_stem = migrated_stem(
        video_path.stem,
        migrated_sidecar,
    )

    if arguments.copy_files is not None:
        assert copy_root is not None

        # Copy mode intentionally flattens every migrated pair into one
        # staging directory for subsequent S3 upload.
        destination_video_path = (
            copy_root /
            (
                destination_stem +
                video_path.suffix
            )
        )

    else:
        destination_video_path = video_path.with_name(
            destination_stem +
            video_path.suffix
        )

    destination_sidecar_path = destination_video_path.with_suffix(
        ".json"
    )

    old_version = optional_int(
        old_sidecar.get(
            "sidecar_version"
        )
    )

    action_text = (
        "COPY"
        if arguments.copy_files is not None
        else "MIGRATE"
    )

    if (
        arguments.copy_files is not None
        and (
            destination_video_path.exists()
            or destination_sidecar_path.exists()
        )
    ):
        print(
            f"SKIP DUPLICATE  {video_path}"
        )
        print(
            f"        -> {destination_video_path}"
        )
        return "skipped_duplicate"

    print(
        f"{action_text} "
        f"v{old_version if old_version is not None else '?'}"
        f"->v{CURRENT_SIDECAR_VERSION}  "
        f"{video_path}"
    )

    provenance = (
        f"  source-folder={source_classification}"
        if source_classification is not None
        else ""
    )

    print(
        "        "
        f"verified={migrated_sidecar['capture']['verified']}  "
        f"classification={migrated_sidecar['capture']['classification']}  "
        f"type={migrated_sidecar['capture']['type']}"
        f"{provenance}"
    )

    if destination_video_path != video_path:
        print(
            f"        -> {destination_video_path}"
        )

    if arguments.dry_run:
        return "would_migrate"

    if arguments.copy_files is not None:
        install_copy(
            video_path,
            destination_video_path,
            destination_sidecar_path,
            migrated_sidecar,
        )
    else:
        install_in_place(
            video_path,
            sidecar_path,
            destination_video_path,
            destination_sidecar_path,
            migrated_sidecar,
        )

    return "migrated"


def collect_video_files(
    target: Path,
    recursive: bool,
    copy_root: Path | None,
) -> list[Path]:
    if target.is_file():
        path = target

        if path.suffix.lower() == ".json":
            path = path.with_suffix(
                ".mp4"
            )

        if path.suffix.lower() != ".mp4":
            raise RuntimeError(
                f"Target file must be MP4 or JSON: {target}"
            )

        if not path.is_file():
            raise RuntimeError(
                f"Matching MP4 not found: {path}"
            )

        return [
            path
        ]

    if not target.is_dir():
        raise RuntimeError(
            f"Target not found: {target}"
        )

    pattern = (
        "**/*.mp4"
        if recursive
        else "*.mp4"
    )

    files: list[Path] = []

    for video_path in sorted(
        target.glob(
            pattern
        )
    ):
        # Never recursively migrate output from a previous/current copy run.
        if copy_root is not None:
            try:
                video_path.relative_to(
                    copy_root
                )
                continue
            except ValueError:
                pass

        files.append(
            video_path
        )

    return files


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Migrate Pi Camera Capture MP4/JSON pairs to sidecar version 7 "
            "without rerunning CandidateFinder or SolutionFilter."
        )
    )

    parser.add_argument(
        "target",
        nargs="?",
        type=Path,
        default=Path("."),
        help=(
            "MP4, JSON, or folder to migrate; defaults to current directory"
        ),
    )

    parser.add_argument(
        "--recursive",
        action="store_true",
        help=(
            "When target is a folder, process subfolders recursively"
        ),
    )

    parser.add_argument(
        "-cf",
        "--copy-files",
        type=Path,
        metavar="OUTPUT_FOLDER",
        default=None,
        help=(
            "Leave originals untouched and write all migrated MP4/JSON pairs "
            "into one flat OUTPUT_FOLDER. Existing destination filenames are "
            "treated as duplicates and skipped."
        ),
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "Report migration and rename actions without changing files"
        ),
    )

    return parser


def main() -> int:
    parser = build_argument_parser()

    arguments = parser.parse_args()

    if (
        arguments.recursive
        and arguments.target.is_file()
    ):
        parser.error(
            "--recursive can only be used with a folder"
        )

    try:
        target = arguments.target.expanduser()

        if target.is_dir():
            target_root = target
        else:
            target_root = target.parent

        copy_root = (
            arguments.copy_files.expanduser()
            if arguments.copy_files is not None
            else None
        )

        if copy_root is not None:
            copy_root.mkdir(
                parents=True,
                exist_ok=True,
            )

        video_files = collect_video_files(
            target,
            arguments.recursive,
            copy_root,
        )

        migrated_count = 0
        skipped_duplicate_count = 0
        rejected_count = 0
        failed_count = 0

        for video_path in video_files:
            try:
                result = process_capture(
                    video_path,
                    arguments,
                    target_root,
                    copy_root,
                )

                if result == "skipped_duplicate":
                    skipped_duplicate_count += 1
                else:
                    migrated_count += 1

            except Exception as error:
                message = str(
                    error
                )

                if (
                    "Source sidecar is incomplete" in message
                    or "analysis-era/incomplete sidecar" in message
                    or "Source camera metadata is incomplete" in message
                    or "Source sidecar has no valid sidecar_version" in message
                ):
                    rejected_count += 1
                    print(
                        f"REJECT  {video_path}: {error}"
                    )
                else:
                    failed_count += 1
                    print(
                        f"FAIL    {video_path}: {error}"
                    )

        print()
        print(
            "Dry run summary:"
            if arguments.dry_run
            else "Summary:"
        )
        print(
            f"  Captures: {len(video_files)}"
        )
        print(
            f"  Migrated: {migrated_count}"
        )
        print(
            f"  Duplicate skips: {skipped_duplicate_count}"
        )
        print(
            f"  Rejected incomplete: {rejected_count}"
        )
        print(
            f"  Failed:   {failed_count}"
        )

        if (
            arguments.copy_files is not None
            and not arguments.dry_run
            and copy_root is not None
        ):
            print(
                f"  Output:   {copy_root}"
            )

        return (
            0
            if (
                failed_count == 0
                and rejected_count == 0
            )
            else 1
        )

    except (
        OSError,
        RuntimeError,
    ) as error:
        print(
            f"Capture migration failed: {error}"
        )
        return 1


if __name__ == "__main__":
    sys.exit(
        main()
    )
