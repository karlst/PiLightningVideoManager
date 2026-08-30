"""Verified copy/move/delete operations for complete capture pairs."""
from __future__ import annotations

from pathlib import Path
from typing import Callable

from camera_capture_manager.camera_registry import CameraDefinition
from camera_capture_manager.pi_connection import PiConnection, RemoteCapture


ProgressCallback = Callable[[str, int, int], None]


def local_capture_status(capture: RemoteCapture, destination: Path) -> str:
    mp4 = destination / f"{capture.stem}.mp4"
    sidecar = destination / f"{capture.stem}.json"

    if not mp4.exists() and not sidecar.exists():
        return "New"

    if mp4.is_file() and sidecar.is_file():
        try:
            if mp4.stat().st_size == capture.mp4_size and sidecar.stat().st_size == capture.json_size:
                return "Already on host"
        except OSError:
            pass

    return "Conflict"


def _copy_one_verified(
    connection: PiConnection,
    remote_path: str,
    expected_size: int,
    local_path: Path,
    progress: ProgressCallback | None,
) -> None:
    temporary = local_path.with_name(local_path.name + ".ccm-part")
    if temporary.exists():
        temporary.unlink()

    def on_progress(transferred: int, total: int) -> None:
        if progress is not None:
            progress(local_path.name, transferred, total)

    try:
        connection.download_file(remote_path, temporary, callback=on_progress)
        actual_size = temporary.stat().st_size
        if actual_size != expected_size:
            raise RuntimeError(
                f"Verification failed for {local_path.name}: "
                f"expected {expected_size} bytes, copied {actual_size}."
            )
        temporary.replace(local_path)
    except Exception:
        if temporary.exists():
            try:
                temporary.unlink()
            except OSError:
                pass
        raise


def copy_capture(
    connection: PiConnection,
    capture: RemoteCapture,
    destination: Path,
    progress: ProgressCallback | None = None,
) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    mp4_local = destination / f"{capture.stem}.mp4"
    json_local = destination / f"{capture.stem}.json"

    # Do not overwrite a conflicting local capture silently.
    status = local_capture_status(capture, destination)
    if status == "Conflict":
        raise RuntimeError(f"Local conflict for {capture.stem}; existing files do not match the Pi.")
    if status == "Already on host":
        return

    _copy_one_verified(connection, capture.mp4_path, capture.mp4_size, mp4_local, progress)
    try:
        _copy_one_verified(connection, capture.json_path, capture.json_size, json_local, progress)
    except Exception:
        # This operation started from a completely new local pair. If the
        # sidecar copy fails, remove the MP4 we just created so a retry starts
        # from a clean state rather than creating a CCM-generated conflict.
        try:
            mp4_local.unlink()
        except OSError:
            pass
        raise


def move_capture(
    connection: PiConnection,
    capture: RemoteCapture,
    destination: Path,
    progress: ProgressCallback | None = None,
) -> None:
    copy_capture(connection, capture, destination, progress)

    # Verify the final local pair immediately before destructive remote delete.
    if local_capture_status(capture, destination) != "Already on host":
        raise RuntimeError(f"Local verification failed; Pi files retained for {capture.stem}.")

    connection.remove_file(capture.mp4_path)
    connection.remove_file(capture.json_path)


def delete_capture(connection: PiConnection, capture: RemoteCapture) -> None:
    connection.remove_file(capture.mp4_path)
    connection.remove_file(capture.json_path)


def perform_batch(
    camera: CameraDefinition,
    captures: list[RemoteCapture],
    destination: Path | None,
    operation: str,
    progress: ProgressCallback | None = None,
) -> tuple[int, list[str]]:
    completed = 0
    errors: list[str] = []

    with PiConnection(camera) as connection:
        for capture in captures:
            try:
                if operation == "copy":
                    assert destination is not None
                    copy_capture(connection, capture, destination, progress)
                elif operation == "move":
                    assert destination is not None
                    move_capture(connection, capture, destination, progress)
                elif operation == "delete":
                    delete_capture(connection, capture)
                else:
                    raise ValueError(f"Unknown transfer operation: {operation}")
                completed += 1
            except Exception as error:
                errors.append(f"{capture.stem}: {error}")

    return completed, errors
