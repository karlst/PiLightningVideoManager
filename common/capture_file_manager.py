"""Local MP4/JSON pair management for batch classification."""

from __future__ import annotations

import shutil
from pathlib import Path


DESTINATION_FOLDERS = {
    "ANOMALY": "anomalies",
    "UNCLASSIFIED": "unclassified",
}


def ensure_destination_folders(input_directory: Path) -> dict[str, Path]:
    destinations: dict[str, Path] = {}
    for category, folder_name in DESTINATION_FOLDERS.items():
        destination = input_directory / folder_name
        destination.mkdir(parents=True, exist_ok=True)
        destinations[category] = destination
    return destinations


def move_file(source: Path, destination_directory: Path) -> None:
    destination = destination_directory / source.name
    if destination.exists():
        raise RuntimeError(f"Destination already exists: {destination}")
    shutil.move(str(source), str(destination))


def delete_capture_pair(video_path: Path, sidecar_path: Path) -> None:
    video_path.unlink(missing_ok=True)
    sidecar_path.unlink(missing_ok=True)


def saved_to_s3_directory(input_directory: Path) -> Path:
    return input_directory / "SavedToS3"


def trim_saved_to_s3(directory: Path, max_pairs: int) -> int:
    if max_pairs < 0:
        raise RuntimeError("saved_to_s3_max_pairs must be non-negative")
    if not directory.is_dir():
        return 0

    pairs: list[tuple[float, Path, Path]] = []
    for video_path in directory.glob("*.mp4"):
        sidecar_path = video_path.with_suffix(".json")
        if not sidecar_path.is_file():
            continue
        try:
            modified_time = video_path.stat().st_mtime
        except OSError:
            continue
        pairs.append((modified_time, video_path, sidecar_path))

    pairs.sort(key=lambda item: item[0])
    remove_count = max(0, len(pairs) - max_pairs)

    for _modified_time, video_path, sidecar_path in pairs[:remove_count]:
        delete_capture_pair(video_path, sidecar_path)

    return remove_count


def move_capture_pair(
    video_path: Path,
    sidecar_path: Path,
    destination_directory: Path,
    copy_only: bool = False,
) -> None:
    video_destination = destination_directory / video_path.name
    sidecar_destination = destination_directory / sidecar_path.name

    if video_destination.exists():
        raise RuntimeError(f"Destination already exists: {video_destination}")
    if sidecar_path.exists() and sidecar_destination.exists():
        raise RuntimeError(f"Destination already exists: {sidecar_destination}")

    if copy_only:
        shutil.copy2(video_path, video_destination)
        if sidecar_path.exists():
            try:
                shutil.copy2(sidecar_path, sidecar_destination)
            except Exception:
                video_destination.unlink(missing_ok=True)
                raise
        return

    move_file(video_path, destination_directory)
    if sidecar_path.exists():
        try:
            move_file(sidecar_path, destination_directory)
        except Exception:
            shutil.move(str(video_destination), str(video_path))
            raise


def move_orphan_sidecars(
    input_directory: Path,
    unclassified_directory: Path,
) -> int:
    moved_count = 0
    for sidecar_path in sorted(input_directory.glob("*.json")):
        video_path = sidecar_path.with_suffix(".mp4")
        if video_path.exists():
            continue
        move_file(sidecar_path, unclassified_directory)
        print(
            f"{sidecar_path.name} -> {unclassified_directory.name} "
            "(orphan JSON sidecar)"
        )
        moved_count += 1
    return moved_count
