"""
@file capture_manager.py

@brief Manages saved capture files.
"""

from pathlib import Path
import time

from cam_config import CamConfig
from event_log import EventLog


class CaptureManager:
    def __init__(
        self,
        config: CamConfig,
        event_log: EventLog
    ) -> None:
        self._config = config
        self._event_log = event_log

        self._capture_directory = (
            config.capture_directory
        )

        self._config.ensure_directories()

    def list_captures(self) -> list[dict]:
        files: list[dict] = []

        if self._capture_directory.exists():
            for path in sorted(
                self._capture_directory.glob(
                    "*.mp4"
                ),
                key=lambda item: item.stat().st_mtime,
                reverse=True
            ):
                files.append(
                    {
                        "name": path.name,
                        "url": f"/capture_files/{path.name}",
                        "size_bytes": path.stat().st_size,
                        "modified_time": path.stat().st_mtime
                    }
                )

        return files

    def cleanup(self) -> None:
        max_files = int(
            self._config.capture_max_files
        )

        protect_recent_seconds = float(
            self._config.capture_protect_recent_seconds
        )

        if max_files <= 0:
            return

        if not self._capture_directory.exists():
            return

        files = sorted(
            self._capture_directory.glob(
                "*.mp4"
            ),
            key=lambda item: item.stat().st_mtime
        )

        delete_count = max(
            0,
            len(files) - max_files
        )

        if delete_count <= 0:
            return

        now_seconds = time.time()
        deleted_count = 0

        for path in files:
            if deleted_count >= delete_count:
                break

            age_seconds = (
                now_seconds -
                path.stat().st_mtime
            )

            if age_seconds < protect_recent_seconds:
                continue

            self._delete_capture_file(
                path
            )

            deleted_count += 1

        if deleted_count > 0:
            self._event_log.add(
                f"Capture cleanup deleted {deleted_count} old file(s)"
            )

    def get_capture_directory(self) -> Path:
        return self._capture_directory

    def _delete_capture_file(
        self,
        path: Path
    ) -> None:
        try:
            path.unlink(
                missing_ok=True
            )

            metadata_path = path.with_suffix(
                ".json"
            )

            metadata_path.unlink(
                missing_ok=True
            )

        except Exception as error:
            self._event_log.add(
                f"Capture cleanup failed for {path.name}: {error}",
                "error"
            )