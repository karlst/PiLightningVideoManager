"""
@file solution_batch.py

@brief Shared batch SolutionFilter engine for saved Candidate captures.

Each Candidate consists of an MP4 plus its matching JSON sidecar. The Pi has
already run CandidateFinder before saving the clip, so BatchClassifier does
NOT replay CandidateFinder and does NOT decode the MP4.

Instead, BatchClassifier trusts the Candidate trigger recorded by the Pi,
reads the per-frame brightness measurements already stored in the sidecar,
and runs the desktop SolutionFilter over the complete Candidate clip.

This separation is intentional:

    Pi CandidateFinder -> decides which clips are worth saving.
    BatchClassifier    -> decides which saved Candidates are Solutions.

Avoiding MP4 decoding makes normal batch classification very fast even for
large folders. The optional --findCandidates mode deliberately reruns
CandidateFinder using the current CandidateConfig or a one-run --sensitivity
override. Because bright-pixel replay
requires reconstructed pixel-change measurements, that mode decodes each MP4
and is therefore much slower.

This module contains the reusable classification and capture-file management
engine shared by the command-line tool and the Pi SolutionFilter service.
SolutionFilter does not migrate sidecars or rename a capture to flash_*.
Current V7 sidecars are required. Recognized anomalies retained by the caller
are automatically marked verified with a final anomaly classification. True
flash candidates remain unverified for human review. Rejected Candidates are
either moved into category subfolders or deleted, according to the caller's mode.
"""

from __future__ import annotations

import contextlib
import io
import json
import shutil
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from common.candidate_config import CANDIDATE_CONFIG
from common.candidate_config import CandidateConfig
from common.capture_sidecar import SIDECAR_VERSION, apply_capture_brightness_summary
from common.aws_auth import AwsAuthConfig, AwsAuthenticator
from common.capture_key import canonical_capture_base_key, pair_keys
from common.s3_store import S3Store, S3StoreError
from video_analyzer.candidate_replay import replay_candidate_finder
from video_analyzer.capture_data import load_capture
from video_analyzer.solution_config import solution_config_for_sensitivity
from video_analyzer.solution_filter import SolutionFilter
from video_analyzer.solution_filter import failed_candidate_result
from video_analyzer.stair_step_decay_filter import CATEGORY_STAIR_STEP_DECAY
from video_analyzer.solution_types import CATEGORY_BRIGHT_NOISE
from video_analyzer.solution_types import CATEGORY_FAILED_CANDIDATE
from video_analyzer.solution_types import CATEGORY_FRAME_DROPOUT
from video_analyzer.solution_types import CATEGORY_STEADY_STATE_CHANGE
from video_analyzer.solution_types import CATEGORY_TRUE_FLASH


DESTINATION_FOLDERS = {
    CATEGORY_FRAME_DROPOUT: "frame_dropout_anomalies",
    CATEGORY_BRIGHT_NOISE: "bright_noise_anomalies",
    CATEGORY_STEADY_STATE_CHANGE: "steady_state_anomalies",
    CATEGORY_STAIR_STEP_DECAY: "stair_step_decay_anomalies",
    CATEGORY_FAILED_CANDIDATE: "not_candidates",
    "UNCLASSIFIED": "unclassified",
}

# Recognized SolutionFilter anomalies are algorithmically adjudicated and do
# not require human verification. Failed candidates/unclassified results are
# intentionally excluded.
ANOMALY_CLASSIFICATION_CODES = {
    CATEGORY_BRIGHT_NOISE: "NA",
    CATEGORY_STEADY_STATE_CHANGE: "SSA",
    CATEGORY_STAIR_STEP_DECAY: "STA",
    CATEGORY_FRAME_DROPOUT: "FDA",
}

# Maximum size of the current PSF activity log before rotation.
PSF_LOG_MAX_BYTES = 10 * 1024

# Prevent the long-running PSF service from writing a START line on every
# periodic run_batch() call. This resets naturally whenever the process restarts.
_psf_start_logged = False


# ## Return the PSF activity-log path beside the captures directory.
def psf_log_path(
    input_directory: Path,
) -> Path:
    return (
        input_directory /
        "logs" /
        "psf.log"
    )


# ## Rotate psf.log to one archive when the next entry would exceed the size limit.
def rotate_psf_log_if_needed(
    log_path: Path,
    additional_bytes: int,
) -> None:
    current_size = 0

    if log_path.exists():
        try:
            current_size = log_path.stat().st_size
        except OSError:
            current_size = 0

    if (
        current_size + additional_bytes
        <= PSF_LOG_MAX_BYTES
    ):
        return

    archive_path = log_path.with_name(
        f"{log_path.name}.archive"
    )

    archive_path.unlink(
        missing_ok=True
    )

    if log_path.exists():
        log_path.replace(
            archive_path
        )


# ## Append one compact UTC-stamped event to the PSF activity log.
def write_psf_log(
    log_path: Path,
    category: str,
    video_name: str = "",
    action: str = "",
    detail: str = "",
) -> None:
    timestamp = datetime.now(
        timezone.utc
    ).strftime(
        "%Y-%m-%d %H:%M:%S"
    )

    fields = [
        timestamp,
        category,
    ]

    if video_name:
        fields.append(
            video_name
        )

    if action:
        fields.append(
            action
        )

    if detail:
        fields.append(
            detail
        )

    line = "  ".join(fields) + "\n"
    additional_bytes = len(
        line.encode("utf-8")
    )

    log_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    rotate_psf_log_if_needed(
        log_path,
        additional_bytes,
    )

    with log_path.open(
        "a",
        encoding="utf-8",
    ) as file:
        file.write(
            line
        )


# ## Read and validate one current V7 JSON sidecar.
def read_sidecar(
    sidecar_path: Path,
) -> dict[str, Any]:
    with sidecar_path.open(
        "r",
        encoding="utf-8",
    ) as file:
        sidecar = json.load(
            file
        )

    if not isinstance(
        sidecar,
        dict,
    ):
        raise RuntimeError(
            "Sidecar root must be a JSON object"
        )

    version = sidecar.get(
        "sidecar_version"
    )

    if version != SIDECAR_VERSION:
        raise RuntimeError(
            f"Sidecar version {version!r} is not supported; "
            "run migrate_capture_files.py first"
        )

    capture = sidecar.get(
        "capture"
    )

    if not isinstance(
        capture,
        dict,
    ):
        raise RuntimeError(
            "V7 sidecar is missing capture metadata; "
            "run migrate_capture_files.py first"
        )

    return sidecar


# ## Atomically persist current capture-level brightness summaries.
def update_capture_brightness_summary(
    sidecar_path: Path,
) -> None:
    sidecar = read_sidecar(
        sidecar_path
    )

    changed = apply_capture_brightness_summary(
        sidecar
    )

    if not changed:
        return

    temporary_path = sidecar_path.with_suffix(
        ".json.tmp"
    )

    temporary_path.write_text(
        json.dumps(
            sidecar,
            indent=4,
        ) + "\n",
        encoding="utf-8",
    )

    with temporary_path.open(
        "r",
        encoding="utf-8",
    ) as file:
        staged = json.load(
            file
        )

    if not isinstance(
        staged,
        dict,
    ):
        temporary_path.unlink(
            missing_ok=True
        )
        raise RuntimeError(
            "Temporary sidecar root is not a JSON object"
        )

    temporary_path.replace(
        sidecar_path
    )


# ## Atomically mark one retained recognized anomaly as verified.
def mark_anomaly_verified(
    sidecar_path: Path,
    category: str,
) -> None:
    classification = ANOMALY_CLASSIFICATION_CODES.get(
        category
    )

    if classification is None:
        return

    sidecar = read_sidecar(
        sidecar_path
    )

    capture = sidecar[
        "capture"
    ]

    capture[
        "verified"
    ] = True
    capture[
        "classification"
    ] = classification
    capture[
        "type"
    ] = "UK"

    apply_capture_brightness_summary(
        sidecar
    )

    temporary_path = sidecar_path.with_suffix(
        ".json.tmp"
    )

    temporary_path.write_text(
        json.dumps(
            sidecar,
            indent=4,
        ) + "\n",
        encoding="utf-8",
    )

    # Verify the staged JSON before replacing the live sidecar.
    with temporary_path.open(
        "r",
        encoding="utf-8",
    ) as file:
        staged = json.load(
            file
        )

    if not isinstance(
        staged,
        dict,
    ):
        temporary_path.unlink(
            missing_ok=True
        )
        raise RuntimeError(
            "Temporary sidecar root is not a JSON object"
        )

    temporary_path.replace(
        sidecar_path
    )



# ## Build the Pi-side S3 store using the restricted ingest profile.
def build_ingest_s3_store() -> S3Store:
    authenticator = AwsAuthenticator(
        AwsAuthConfig(
            profile_name="picam-ingest",
        )
    )

    try:
        credential_document = json.loads(
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
        credential_document.get(
            "bucket",
            "",
        ) or ""
    ).strip()

    if not bucket_name:
        raise RuntimeError(
            "AWS credential file is missing bucket name"
        )

    return S3Store(
        bucket_name,
        authenticator,
    )


# ## Upload one capture pair under its canonical post-filter V7 key.
def upload_capture_pair_to_s3(
    store: S3Store,
    video_path: Path,
    sidecar_path: Path,
) -> str:
    sidecar = read_sidecar(
        sidecar_path
    )

    base_key = canonical_capture_base_key(
        sidecar,
        fallback_stem=video_path.stem,
    )

    # Timing-test captures carry an explicit top-level test marker. Keep their
    # otherwise-canonical keys under one disposable S3 prefix so test data can
    # be inspected or deleted independently of real captures.
    test_metadata = sidecar.get(
        "test"
    )

    if isinstance(
        test_metadata,
        dict,
    ):
        test_kind = str(
            test_metadata.get(
                "kind",
                "",
            ) or ""
        ).strip()

        test_run_id = str(
            test_metadata.get(
                "run_id",
                "",
            ) or ""
        ).strip()

        if (
            test_kind == "capture_timing"
            and test_run_id
        ):
            safe_run_id = (
                test_run_id
                .replace(
                    "/",
                    "_",
                )
                .replace(
                    "\\",
                    "_",
                )
            )

            base_key = (
                f"test/{safe_run_id}/"
                f"{base_key}"
            )

    mp4_key, json_key = pair_keys(
        base_key
    )

    mp4_exists = store.object_exists(
        mp4_key
    )
    json_exists = store.object_exists(
        json_key
    )

    if not mp4_exists:
        store.upload_file(
            video_path,
            mp4_key,
        )

    if not json_exists:
        store.upload_file(
            sidecar_path,
            json_key,
        )

    return base_key


# ## Build SolutionFilter input arrays from brightness data already saved by the Pi.
def build_metric_arrays(
    sidecar: dict[str, Any],
) -> tuple[np.ndarray, np.ndarray]:
    records = sidecar.get(
        "frame_records",
        [],
    )

    if not isinstance(records, list) or not records:
        raise RuntimeError(
            "Sidecar contains no frame_records"
        )

    brightness_values: list[float] = []
    delta_values: list[float] = []

    for record in records:
        if not isinstance(record, dict):
            raise RuntimeError(
                "Invalid frame record"
            )

        try:
            brightness_values.append(
                float(record["mean_brightness"])
            )
            delta_values.append(
                float(
                    record[
                        "brightness_delta_adjacent"
                    ]
                )
            )
        except (
            KeyError,
            TypeError,
            ValueError,
        ) as error:
            raise RuntimeError(
                "Frame record is missing valid brightness metrics"
            ) from error

    return (
        np.asarray(
            brightness_values,
            dtype=np.float64,
        ),
        np.asarray(
            delta_values,
            dtype=np.float64,
        ),
    )


# ## Return the Candidate trigger frame recorded by the Pi.
def get_trigger_frame_index(
    sidecar: dict[str, Any],
) -> int | None:
    # Current sidecars store Candidate information in a nested object.
    candidate = sidecar.get(
        "candidate"
    )

    if isinstance(candidate, dict):
        value = candidate.get(
            "trigger_frame_index"
        )

        if value is not None:
            try:
                return int(value)
            except (TypeError, ValueError):
                return None

        frame_number = candidate.get(
            "trigger_frame_number"
        )

        if frame_number is not None:
            try:
                return int(frame_number) - 1
            except (TypeError, ValueError):
                return None

    # Legacy/reconstructed sidecars may store trigger fields at the root.
    value = sidecar.get(
        "trigger_frame_index"
    )

    if value is not None:
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    frame_number = sidecar.get(
        "trigger_frame_number"
    )

    if frame_number is not None:
        try:
            return int(frame_number) - 1
        except (TypeError, ValueError):
            return None

    return None


# ## Create all category destination folders and return their paths.
def ensure_destination_folders(
    input_directory: Path,
) -> dict[str, Path]:
    destinations: dict[str, Path] = {}

    for category, folder_name in (
        DESTINATION_FOLDERS.items()
    ):
        destination = (
            input_directory /
            folder_name
        )

        destination.mkdir(
            parents=True,
            exist_ok=True,
        )

        destinations[
            category
        ] = destination

    return destinations


# ## Move one file without ever overwriting an existing destination file.
def move_file(
    source: Path,
    destination_directory: Path,
) -> None:
    destination = (
        destination_directory /
        source.name
    )

    if destination.exists():
        raise RuntimeError(
            f"Destination already exists: {destination}"
        )

    shutil.move(
        str(source),
        str(destination),
    )





# ## Delete an MP4 and its matching sidecar without touching unrelated files.
def delete_capture_pair(
    video_path: Path,
    sidecar_path: Path,
) -> None:
    video_path.unlink(
        missing_ok=True
    )

    sidecar_path.unlink(
        missing_ok=True
    )


# ## Move an MP4 and matching sidecar together, rolling back if the second move fails.
def move_capture_pair(
    video_path: Path,
    sidecar_path: Path,
    destination_directory: Path,
    copy_only: bool = False,
) -> None:
    video_destination = destination_directory / video_path.name
    sidecar_destination = destination_directory / sidecar_path.name

    if video_destination.exists():
        raise RuntimeError(
            f"Destination already exists: {video_destination}"
        )

    if sidecar_path.exists() and sidecar_destination.exists():
        raise RuntimeError(
            f"Destination already exists: {sidecar_destination}"
        )

    if copy_only:
        shutil.copy2(
            video_path,
            video_destination,
        )

        if sidecar_path.exists():
            try:
                shutil.copy2(
                    sidecar_path,
                    sidecar_destination,
                )
            except Exception:
                video_destination.unlink(missing_ok=True)
                raise

        return

    move_file(
        video_path,
        destination_directory,
    )

    if sidecar_path.exists():
        try:
            move_file(
                sidecar_path,
                destination_directory,
            )
        except Exception:
            shutil.move(
                str(video_destination),
                str(video_path),
            )
            raise


# ## Classify one capture using either the recorded trigger or current Candidate settings.
def classify_capture(
    video_path: Path,
    solution_filter: SolutionFilter,
    candidate_config: CandidateConfig = CANDIDATE_CONFIG,
    find_candidates: bool = False,
    verbosity: int = 0,
) -> tuple[str, str]:
    sidecar_path = video_path.with_suffix(
        ".json"
    )

    if not sidecar_path.is_file():
        return (
            "UNCLASSIFIED",
            "Matching JSON sidecar not found",
        )

    try:
        # Experimental mode: rerun CandidateFinder using CURRENT CandidateConfig.
        # This is intentionally slower because bright-pixel replay requires
        # decoding the MP4 and reconstructing per-frame pixel-change metrics.
        if find_candidates:
            if verbosity >= 2:
                capture_data = load_capture(
                    video_path
                )
            else:
                with contextlib.redirect_stdout(
                    io.StringIO()
                ):
                    capture_data = load_capture(
                        video_path
                    )

            candidate_result = replay_candidate_finder(
                capture_data,
                candidate_config,
            )

            if candidate_result.frame_index is None:
                result = failed_candidate_result()

                return (
                    result.category,
                    result.reason,
                )

            result = solution_filter.evaluate(
                capture_data.pi_brightness,
                capture_data.pi_brightness_delta,
                candidate_result.frame_index,
                candidate_result.reason,
            )

            return (
                result.category,
                result.reason,
            )

        # Normal fast mode: trust the Candidate trigger already recorded by Pi.
        sidecar = read_sidecar(
            sidecar_path
        )

        (
            brightness,
            brightness_delta,
        ) = build_metric_arrays(
            sidecar
        )

        trigger_frame_index = (
            get_trigger_frame_index(
                sidecar
            )
        )

        if trigger_frame_index is None:
            return (
                "UNCLASSIFIED",
                "Sidecar contains no valid Candidate trigger frame",
            )

        if not 0 <= trigger_frame_index < len(brightness):
            return (
                "UNCLASSIFIED",
                "Candidate trigger frame is outside frame_records",
            )

        # Preserve the CandidateFinder reason recorded by the Pi so
        # trigger-specific SolutionFilter rules can run in the fast path.
        trigger_reason = ""

        candidate = sidecar.get(
            "candidate"
        )

        if isinstance(candidate, dict):
            trigger_reason = str(
                candidate.get(
                    "trigger_reason",
                    ""
                )
            )
        else:
            # Legacy/reconstructed sidecars may store trigger fields at root.
            trigger_reason = str(
                sidecar.get(
                    "trigger_reason",
                    ""
                )
            )

        result = solution_filter.evaluate(
            brightness,
            brightness_delta,
            trigger_frame_index,
            trigger_reason,
        )

        return (
            result.category,
            result.reason,
        )

    except (
        OSError,
        json.JSONDecodeError,
        RuntimeError,
    ) as error:
        return (
            "UNCLASSIFIED",
            str(error),
        )


# ## Move JSON files that have no matching MP4 into the unclassified folder.
def move_orphan_sidecars(
    input_directory: Path,
    unclassified_directory: Path,
) -> int:
    moved_count = 0

    for sidecar_path in sorted(
        input_directory.glob("*.json")
    ):
        video_path = sidecar_path.with_suffix(
            ".mp4"
        )

        if video_path.exists():
            continue

        move_file(
            sidecar_path,
            unclassified_directory,
        )

        print(
            f"{sidecar_path.name} -> "
            f"{unclassified_directory.name} "
            "(orphan JSON sidecar)"
        )

        moved_count += 1

    return moved_count


# ## Classify every pending capture_* Candidate in one captures folder.
def run_batch_solution_filter(
    input_directory: Path,
    verbosity: int = 0,
    copy_only: bool = False,
    delete_rejects: bool = False,
    move_to_subfolders: bool = False,
    find_candidates: bool = False,
    upload_to_s3: bool = False,
    candidate_config: CandidateConfig = CANDIDATE_CONFIG,
) -> int:
    if not input_directory.is_dir():
        raise RuntimeError(
            f"Folder not found: {input_directory}"
        )

    if copy_only and delete_rejects:
        raise RuntimeError(
            "--copy and --delete-rejects cannot be used together"
        )

    if move_to_subfolders and delete_rejects:
        raise RuntimeError(
            "--move-to-subfolders and --delete-rejects cannot be used together"
        )

    if copy_only and move_to_subfolders:
        raise RuntimeError(
            "--copy and --move-to-subfolders cannot be used together"
        )

    if (
        upload_to_s3
        and (
            copy_only
            or move_to_subfolders
        )
    ):
        raise RuntimeError(
            "S3 upload is supported only by the in-place PSF workflow"
        )

    global _psf_start_logged

    log_path = (
        psf_log_path(input_directory)
        if (
            delete_rejects
            or upload_to_s3
        )
        else None
    )

    if (
        delete_rejects
        and log_path is not None
        and not _psf_start_logged
    ):
        write_psf_log(
            log_path,
            "START",
            detail=(
                f"captures={input_directory}"
            ),
        )
        _psf_start_logged = True

    destinations = (
        ensure_destination_folders(
            input_directory
        )
        if (
            copy_only
            or move_to_subfolders
        )
        else {}
    )

    copy_true_flash_directory = None

    if copy_only:
        copy_true_flash_directory = (
            input_directory / "true_flashes"
        )
        copy_true_flash_directory.mkdir(
            parents=True,
            exist_ok=True,
        )

    solution_filter = SolutionFilter(
        solution_config_for_sensitivity(
            candidate_config.sensitivity
        )
    )
    counts: Counter[str] = Counter()

    s3_store: S3Store | None = None

    if upload_to_s3:
        s3_store = build_ingest_s3_store()

    # Only pending capture_* files are batch-filtered. Verified flash_* files
    # are owned by the human-review workflow and are not reprocessed here.
    video_files = sorted(
        input_directory.glob(
            "capture_*.mp4"
        )
    )

    for video_path in video_files:
        sidecar_path = video_path.with_suffix(
            ".json"
        )

        try:
            update_capture_brightness_summary(
                sidecar_path
            )
        except (
            OSError,
            json.JSONDecodeError,
            RuntimeError,
        ) as error:
            print(
                f"SKIP  {video_path.name}: {error}"
            )
            continue

        category, reason = classify_capture(
            video_path,
            solution_filter,
            candidate_config=candidate_config,
            find_candidates=find_candidates,
            verbosity=verbosity,
        )

        try:
            # Finalize any algorithmically verified anomaly BEFORE deriving the
            # canonical S3 key. True-flash candidates remain unverified.
            if category in ANOMALY_CLASSIFICATION_CODES:
                mark_anomaly_verified(
                    sidecar_path,
                    category,
                )

            if (
                upload_to_s3
                and s3_store is not None
                and category in (
                    CATEGORY_TRUE_FLASH,
                    CATEGORY_BRIGHT_NOISE,
                    CATEGORY_STEADY_STATE_CHANGE,
                    CATEGORY_STAIR_STEP_DECAY,
                    CATEGORY_FRAME_DROPOUT,
                )
            ):
                try:
                    base_key = upload_capture_pair_to_s3(
                        s3_store,
                        video_path,
                        sidecar_path,
                    )

                    if log_path is not None:
                        write_psf_log(
                            log_path,
                            "S3",
                            video_path.name,
                            "UPLOADED",
                            base_key,
                        )

                    if verbosity >= 1:
                        print(
                            f"{video_path.name} -> S3: {base_key}"
                        )

                except (
                    OSError,
                    RuntimeError,
                    ValueError,
                    S3StoreError,
                ) as error:
                    if log_path is not None:
                        write_psf_log(
                            log_path,
                            "S3_ERROR",
                            video_path.name,
                            "KEPT_LOCAL",
                            str(error),
                        )

                    print(
                        f"KEEP  {video_path.name}: "
                        f"S3 upload failed: {error}"
                    )

                    # Never delete or move a capture whose requested S3 upload
                    # failed. Leave the pair in place for the next PSF pass.
                    continue

            if category == CATEGORY_TRUE_FLASH:
                if copy_only:
                    assert copy_true_flash_directory is not None

                    move_capture_pair(
                        video_path,
                        sidecar_path,
                        copy_true_flash_directory,
                        copy_only=True,
                    )

                    if verbosity >= 1:
                        print(
                            f"{video_path.name} -> "
                            f"{copy_true_flash_directory.name} "
                            f"(copied): {reason}"
                        )
                else:
                    # True-flash candidates require human review. SolutionFilter
                    # does not verify or rename them.
                    if verbosity >= 1:
                        print(
                            f"{video_path.name} -> "
                            f"UNCHANGED: {reason}"
                        )

            elif delete_rejects:
                delete_capture_pair(
                    video_path,
                    sidecar_path,
                )

                if log_path is not None:
                    write_psf_log(
                        log_path,
                        category,
                        video_path.name,
                        "DELETED",
                    )

                if verbosity >= 1:
                    print(
                        f"{video_path.name} -> DELETED: {reason}"
                    )

            elif copy_only:
                destination_directory = destinations[
                    category
                ]

                move_capture_pair(
                    video_path,
                    sidecar_path,
                    destination_directory,
                    copy_only=True,
                )

                # Mark only the retained destination copy. The source remains
                # untouched, preserving copy semantics.
                if category in ANOMALY_CLASSIFICATION_CODES:
                    mark_anomaly_verified(
                        destination_directory / sidecar_path.name,
                        category,
                    )

                if verbosity >= 1:
                    print(
                        f"{video_path.name} -> "
                        f"{destination_directory.name} "
                        f"(copied): {reason}"
                    )

            elif move_to_subfolders:
                destination_directory = destinations[
                    category
                ]

                move_capture_pair(
                    video_path,
                    sidecar_path,
                    destination_directory,
                    copy_only=False,
                )

                if verbosity >= 1:
                    print(
                        f"{video_path.name} -> "
                        f"{destination_directory.name}: {reason}"
                    )

            else:
                # Default production behavior: keep retained captures exactly
                # where they are. Recognized anomalies are automatically
                # adjudicated as verified in their existing sidecars.
                if category in ANOMALY_CLASSIFICATION_CODES:
                    if verbosity >= 1:
                        print(
                            f"{video_path.name} -> "
                            f"VERIFIED IN PLACE: {reason}"
                        )
                elif verbosity >= 1:
                    print(
                        f"{video_path.name} -> "
                        f"UNCHANGED: {reason}"
                    )

        except RuntimeError as error:
            print(
                f"SKIP  {video_path.name}: "
                f"{error}"
            )
            if delete_rejects and log_path is not None:
                write_psf_log(
                    log_path,
                    "ERROR",
                    video_path.name,
                    "SKIPPED",
                    str(error),
                )
            continue

        counts[category] += 1

    orphan_count = 0

    if move_to_subfolders:
        orphan_count = move_orphan_sidecars(
            input_directory,
            destinations["UNCLASSIFIED"],
        )

    counts["UNCLASSIFIED"] += orphan_count

    print()
    print("Summary:")
    print(
        f"  True flashes: "
        f"{counts[CATEGORY_TRUE_FLASH]}"
    )
    print(
        f"  Frame dropout anomalies: "
        f"{counts[CATEGORY_FRAME_DROPOUT]}"
    )
    print(
        f"  Bright noise anomalies: "
        f"{counts[CATEGORY_BRIGHT_NOISE]}"
    )
    print(
        f"  Steady-state anomalies: "
        f"{counts[CATEGORY_STEADY_STATE_CHANGE]}"
    )
    print(
        f"  Stair-step decay anomalies: "
        f"{counts[CATEGORY_STAIR_STEP_DECAY]}"
    )
    print(
        f"  Not candidates: "
        f"{counts[CATEGORY_FAILED_CANDIDATE]}"
    )
    print(
        f"  Unclassified: "
        f"{counts['UNCLASSIFIED']}"
    )

    if delete_rejects:
        deleted_count = (
            counts[CATEGORY_FRAME_DROPOUT]
            + counts[CATEGORY_BRIGHT_NOISE]
            + counts[CATEGORY_STEADY_STATE_CHANGE]
            + counts[CATEGORY_STAIR_STEP_DECAY]
            + counts[CATEGORY_FAILED_CANDIDATE]
            + counts["UNCLASSIFIED"]
        )

        print(
            f"  Deleted: {deleted_count}"
        )

    return 0
