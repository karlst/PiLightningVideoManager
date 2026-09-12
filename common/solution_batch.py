"""
@file solution_batch.py

@brief Batch coordinator for the production Pi Camera capture classifier.

This module deliberately contains orchestration, not the trained model.  Each
pending capture_* MP4/JSON pair is read from its V8 sidecar, classified by the
frozen logistic-regression model in common.classification_model, finalized in
its sidecar with FLASH/ANOMALY plus initial confidence, and then handled according to
local-retention and S3 policy.

Production classification is sidecar-only and has no dependency on the legacy
SolutionFilter or solution_config modules.  Optional --findCandidates mode may
rerun CandidateFinder against the MP4 to select a trigger, but the resulting
capture is still classified only by the frozen logistic model.

Supporting responsibilities are split into focused modules:

    classification_model.py   trained feature extraction and logistic model
    sidecar_store.py           V8 sidecar read/update operations
    capture_file_manager.py    local MP4/JSON pair operations
    capture_s3_uploader.py     canonical pair upload and rollback
    capture_key.py             canonical V8 S3 key construction

The validated model mathematics are intentionally isolated from file/S3 policy
so refactoring those workflows cannot silently change classification behavior.
"""

from __future__ import annotations

import contextlib
import io
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from common.candidate_config import CANDIDATE_CONFIG, CandidateConfig
from common.capture_file_manager import delete_capture_pair
from common.capture_file_manager import ensure_destination_folders
from common.capture_file_manager import move_capture_pair
from common.capture_file_manager import move_orphan_sidecars
from common.capture_file_manager import saved_to_s3_directory
from common.capture_file_manager import trim_saved_to_s3
from common.capture_s3_uploader import build_ingest_s3_store
from common.capture_s3_uploader import upload_capture_pair_to_s3
from common.classification_model import CLASSIFICATION_ANOMALY
from common.classification_model import CLASSIFICATION_FLASH
from common.classification_model import ClassificationResult
from common.classification_model import classify_arrays
from common.s3_store import S3Store, S3StoreError
from common.sidecar_store import apply_classification_result
from common.sidecar_store import build_metric_arrays
from common.sidecar_store import get_trigger_frame_index
from common.sidecar_store import read_sidecar
from common.sidecar_store import update_capture_brightness_summary
from common.system_config import load_system_settings
from video_analyzer.candidate_replay import replay_candidate_finder
from video_analyzer.capture_data import load_capture


CATEGORY_UNCLASSIFIED = "UNCLASSIFIED"
PSF_LOG_MAX_BYTES = 10 * 1024
_psf_start_logged = False


def psf_log_path(input_directory: Path) -> Path:
    return input_directory / "logs" / "psf.log"


def rotate_psf_log_if_needed(log_path: Path, additional_bytes: int) -> None:
    current_size = 0
    if log_path.exists():
        try:
            current_size = log_path.stat().st_size
        except OSError:
            current_size = 0

    if current_size + additional_bytes <= PSF_LOG_MAX_BYTES:
        return

    archive_path = log_path.with_name(f"{log_path.name}.archive")
    archive_path.unlink(missing_ok=True)
    if log_path.exists():
        log_path.replace(archive_path)


def write_psf_log(
    log_path: Path,
    category: str,
    video_name: str = "",
    action: str = "",
    detail: str = "",
) -> None:
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    fields = [timestamp, category]
    if video_name:
        fields.append(video_name)
    if action:
        fields.append(action)
    if detail:
        fields.append(detail)

    line = "  ".join(fields) + "\n"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    rotate_psf_log_if_needed(log_path, len(line.encode("utf-8")))
    with log_path.open("a", encoding="utf-8") as file:
        file.write(line)


def classify_solution_arrays(
    brightness,
    brightness_delta,
    trigger_frame_index: int,
) -> ClassificationResult:
    """Public sidecar-array entry point for the frozen production classifier."""
    return classify_arrays(brightness, brightness_delta, trigger_frame_index)


def classify_capture(
    video_path: Path,
    candidate_config: CandidateConfig = CANDIDATE_CONFIG,
    find_candidates: bool = False,
    verbosity: int = 0,
) -> ClassificationResult | tuple[str, str]:
    """Classify one capture using its recorded trigger or optional replay trigger."""
    sidecar_path = video_path.with_suffix(".json")
    if not sidecar_path.is_file():
        return CATEGORY_UNCLASSIFIED, "Matching JSON sidecar not found"

    try:
        if find_candidates:
            if verbosity >= 2:
                capture_data = load_capture(video_path)
            else:
                with contextlib.redirect_stdout(io.StringIO()):
                    capture_data = load_capture(video_path)

            candidate_result = replay_candidate_finder(
                capture_data,
                candidate_config,
            )
            if candidate_result.frame_index is None:
                return (
                    CATEGORY_UNCLASSIFIED,
                    "CandidateFinder replay found no trigger",
                )

            # Step 1 - Supply the replay brightness arrays and selected trigger.
            return classify_solution_arrays(
                capture_data.pi_brightness,
                capture_data.pi_brightness_delta,
                candidate_result.frame_index,
            )

        sidecar = read_sidecar(sidecar_path)
        brightness, brightness_delta = build_metric_arrays(sidecar)
        trigger_frame_index = get_trigger_frame_index(sidecar)

        if trigger_frame_index is None:
            return (
                CATEGORY_UNCLASSIFIED,
                "Sidecar contains no valid Candidate trigger frame",
            )
        if not 0 <= trigger_frame_index < len(brightness):
            return (
                CATEGORY_UNCLASSIFIED,
                "Candidate trigger frame is outside frame_records",
            )

        # Step 1 - Supply the sidecar brightness arrays and recorded Pi trigger.
        return classify_solution_arrays(
            brightness,
            brightness_delta,
            trigger_frame_index,
        )

    except (OSError, json.JSONDecodeError, RuntimeError) as error:
        return CATEGORY_UNCLASSIFIED, str(error)


def run_batch_solution_filter(
    input_directory: Path,
    verbosity: int = 0,
    copy_only: bool = False,
    delete_rejects: bool = False,
    move_to_subfolders: bool = False,
    find_candidates: bool = False,
    upload_to_s3: bool = False,
    candidate_config: CandidateConfig = CANDIDATE_CONFIG,
    return_summary: bool = False,
) -> int | dict:
    """Classify every pending capture_* pair in one captures folder."""
    if not input_directory.is_dir():
        raise RuntimeError(f"Folder not found: {input_directory}")

    if copy_only and delete_rejects:
        raise RuntimeError("--copy and --delete-rejects cannot be used together")
    if move_to_subfolders and delete_rejects:
        raise RuntimeError(
            "--move-to-subfolders and --delete-rejects cannot be used together"
        )
    if copy_only and move_to_subfolders:
        raise RuntimeError("--copy and --move-to-subfolders cannot be used together")
    if upload_to_s3 and (copy_only or move_to_subfolders):
        raise RuntimeError("S3 upload is supported only by the in-place PSF workflow")

    global _psf_start_logged

    log_path = (
        psf_log_path(input_directory)
        if delete_rejects or upload_to_s3
        else None
    )

    if delete_rejects and log_path is not None and not _psf_start_logged:
        write_psf_log(log_path, "START", detail=f"captures={input_directory}")
        _psf_start_logged = True

    destinations = (
        ensure_destination_folders(input_directory)
        if copy_only or move_to_subfolders
        else {}
    )

    copy_flash_directory: Path | None = None
    if copy_only:
        copy_flash_directory = input_directory / "flashes"
        copy_flash_directory.mkdir(parents=True, exist_ok=True)

    counts: Counter[str] = Counter()
    new_classification_counts: Counter[str] = Counter()
    s3_uploaded_capture_count = 0
    s3_failed_capture_count = 0
    s3_store: S3Store | None = None
    saved_directory: Path | None = None
    saved_max_pairs = 100
    save_filtered_false_positives = False

    if upload_to_s3:
        system_settings = load_system_settings()
        saved_max_pairs = int(system_settings.get("saved_to_s3_max_pairs", 100))
        save_filtered_false_positives = bool(
            system_settings.get("save_filtered_false_positives", False)
        )
        if saved_max_pairs < 0:
            raise RuntimeError("saved_to_s3_max_pairs must be non-negative")

        s3_store = build_ingest_s3_store()
        saved_directory = saved_to_s3_directory(input_directory)
        saved_directory.mkdir(parents=True, exist_ok=True)

    video_files = sorted(input_directory.glob("capture_*.mp4"))

    for video_path in video_files:
        sidecar_path = video_path.with_suffix(".json")

        try:
            update_capture_brightness_summary(sidecar_path)
            sidecar_before = read_sidecar(sidecar_path)
            capture_before = sidecar_before.get("capture", {})
            current_classification = str(
                capture_before.get("classification", "")
                if isinstance(capture_before, dict)
                else ""
            ).strip().upper()
            was_pending_classification = current_classification in ("", "PENDING")
        except (OSError, json.JSONDecodeError, RuntimeError) as error:
            print(f"SKIP  {video_path.name}: {error}")
            counts[CATEGORY_UNCLASSIFIED] += 1
            continue

        classified = classify_capture(
            video_path,
            candidate_config=candidate_config,
            find_candidates=find_candidates,
            verbosity=verbosity,
        )

        if isinstance(classified, tuple):
            category, reason = classified
            if verbosity >= 1:
                print(f"{video_path.name} -> {category}: {reason}")
            counts[category] += 1
            continue

        result = classified
        category = result.classification
        reason = result.reason

        # Operational telemetry counts a capture's initial production
        # classification once. A retained pair may be revisited later for an
        # S3 retry; that must not inflate FLASH/ANOMALY activity counts.
        if was_pending_classification:
            new_classification_counts[category] += 1

        try:
            # Persist FLASH/ANOMALY, initial confidence and model identity before any
            # canonical S3 key is derived or any retained copy is made.
            apply_classification_result(sidecar_path, result)

            archived_to_s3 = False
            should_upload = (
                upload_to_s3
                and s3_store is not None
                and (
                    category == CLASSIFICATION_FLASH
                    or (
                        category == CLASSIFICATION_ANOMALY
                        and save_filtered_false_positives
                    )
                )
            )

            if should_upload:
                try:
                    base_key = upload_capture_pair_to_s3(
                        s3_store,
                        video_path,
                        sidecar_path,
                    )
                    s3_uploaded_capture_count += 1

                    if log_path is not None:
                        write_psf_log(
                            log_path,
                            "S3",
                            video_path.name,
                            "UPLOADED",
                            base_key,
                        )
                    if verbosity >= 1:
                        print(f"{video_path.name} -> S3: {base_key}")

                    assert saved_directory is not None
                    move_capture_pair(
                        video_path,
                        sidecar_path,
                        saved_directory,
                        copy_only=False,
                    )
                    archived_to_s3 = True

                    trimmed_count = trim_saved_to_s3(
                        saved_directory,
                        saved_max_pairs,
                    )
                    if log_path is not None:
                        write_psf_log(
                            log_path,
                            "LOCAL",
                            video_path.name,
                            "MOVED_TO_SAVED_TO_S3",
                            f"max_pairs={saved_max_pairs}; trimmed={trimmed_count}",
                        )
                    if verbosity >= 1:
                        print(
                            f"{video_path.name} -> {saved_directory.name}; "
                            f"trimmed={trimmed_count}"
                        )

                except (OSError, RuntimeError, ValueError, S3StoreError) as error:
                    s3_failed_capture_count += 1
                    if log_path is not None:
                        write_psf_log(
                            log_path,
                            "S3_ERROR",
                            video_path.name,
                            "KEPT_LOCAL",
                            str(error),
                        )
                    print(f"KEEP  {video_path.name}: S3 upload failed: {error}")
                    # Keep the complete local pair for a later PSF retry.
                    continue

            if archived_to_s3:
                pass

            elif category == CLASSIFICATION_FLASH:
                if copy_only:
                    assert copy_flash_directory is not None
                    move_capture_pair(
                        video_path,
                        sidecar_path,
                        copy_flash_directory,
                        copy_only=True,
                    )
                    if verbosity >= 1:
                        print(
                            f"{video_path.name} -> {copy_flash_directory.name} "
                            f"(copied): {reason}"
                        )
                elif verbosity >= 1:
                    print(f"{video_path.name} -> FLASH, AWAITING REVIEW: {reason}")

            elif category == CLASSIFICATION_ANOMALY:
                if delete_rejects:
                    delete_capture_pair(video_path, sidecar_path)
                    if log_path is not None:
                        write_psf_log(
                            log_path,
                            CLASSIFICATION_ANOMALY,
                            video_path.name,
                            "DELETED",
                            f"initial_confidence={1.0 - result.flash_probability:.4f}",
                        )
                    if verbosity >= 1:
                        print(f"{video_path.name} -> DELETED: {reason}")

                elif copy_only:
                    destination_directory = destinations[CLASSIFICATION_ANOMALY]
                    move_capture_pair(
                        video_path,
                        sidecar_path,
                        destination_directory,
                        copy_only=True,
                    )
                    if verbosity >= 1:
                        print(
                            f"{video_path.name} -> {destination_directory.name} "
                            f"(copied): {reason}"
                        )

                elif move_to_subfolders:
                    destination_directory = destinations[CLASSIFICATION_ANOMALY]
                    move_capture_pair(
                        video_path,
                        sidecar_path,
                        destination_directory,
                        copy_only=False,
                    )
                    if verbosity >= 1:
                        print(
                            f"{video_path.name} -> {destination_directory.name}: {reason}"
                        )

                elif verbosity >= 1:
                    print(f"{video_path.name} -> VERIFIED ANOMALY IN PLACE: {reason}")

        except RuntimeError as error:
            print(f"SKIP  {video_path.name}: {error}")
            if delete_rejects and log_path is not None:
                write_psf_log(
                    log_path,
                    "ERROR",
                    video_path.name,
                    "SKIPPED",
                    str(error),
                )
            counts[CATEGORY_UNCLASSIFIED] += 1
            continue

        counts[category] += 1

    if upload_to_s3 and log_path is not None:
        if s3_uploaded_capture_count > 0:
            write_psf_log(
                log_path,
                "S3",
                action="UPLOAD_SUMMARY",
                detail=(
                    f"{s3_uploaded_capture_count} capture"
                    f"{'' if s3_uploaded_capture_count == 1 else 's'} uploaded"
                ),
            )
        if s3_failed_capture_count > 0:
            write_psf_log(
                log_path,
                "S3_ERROR",
                action="UPLOAD_SUMMARY",
                detail=(
                    f"{s3_failed_capture_count} capture"
                    f"{'' if s3_failed_capture_count == 1 else 's'} failed"
                ),
            )

    orphan_count = 0
    if move_to_subfolders:
        orphan_count = move_orphan_sidecars(
            input_directory,
            destinations[CATEGORY_UNCLASSIFIED],
        )
    counts[CATEGORY_UNCLASSIFIED] += orphan_count

    print()
    print("Summary:")
    print(f"  Flashes: {counts[CLASSIFICATION_FLASH]}")
    print(f"  Anomalies: {counts[CLASSIFICATION_ANOMALY]}")
    print(f"  Unclassified: {counts[CATEGORY_UNCLASSIFIED]}")

    if delete_rejects:
        print(f"  Deleted: {counts[CLASSIFICATION_ANOMALY]}")

    if return_summary:
        return {
            "flash": int(new_classification_counts[CLASSIFICATION_FLASH]),
            "anomaly": int(new_classification_counts[CLASSIFICATION_ANOMALY]),
            "unclassified": int(counts[CATEGORY_UNCLASSIFIED]),
            "s3_success": int(s3_uploaded_capture_count),
            "s3_failure": int(s3_failed_capture_count),
        }

    return 0
