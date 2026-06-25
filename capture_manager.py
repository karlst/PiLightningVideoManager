"""
@file capture_manager.py

@brief Manages saved capture files.
"""

from pathlib import Path
import json
import re
import time

from cam_config import CamConfig
from event_log import EventLog


class CaptureManager:
    # ## Initialize capture storage and event logging.
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

    # ## List captures with sidecar summary fields for the browser UI.
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
                # Keep all sidecar data in the capture record so playback
                # can display the full analysis without another server call.
                sidecar = self._read_sidecar(
                    path
                )

                files.append(
                    {
                        "name": path.name,
                        "display_name": self._get_display_name(
                            path
                        ),
                        "url": f"/capture_files/{path.name}",
                        "size_bytes": path.stat().st_size,
                        "modified_time": path.stat().st_mtime,
                        "longest_event_ms": sidecar.get(
                            "longest_event_ms",
                            None
                        ),
                        "valid_component_count": sidecar.get(
                            "valid_component_count",
                            None
                        ),
                        "analysis": sidecar
                    }
                )

        return files

    # ## Delete old capture files when the capture limit is exceeded.
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

    # ## Return the directory containing MP4 captures and JSON sidecars.
    def get_capture_directory(self) -> Path:
        return self._capture_directory

    # ## Read the JSON sidecar for one capture file.
    def _read_sidecar(
        self,
        path: Path
    ) -> dict:
        sidecar: dict = {}

        sidecar_path = path.with_suffix(
            ".json"
        )

        if sidecar_path.exists():
            try:
                sidecar = json.loads(
                    sidecar_path.read_text(
                        encoding="utf-8"
                    )
                )

            except Exception as error:
                self._event_log.add(
                    f"Capture sidecar read failed for {path.name}: {error}",
                    "error"
                )

                sidecar = {}

        return sidecar

    # ## Build the compact display name used in the capture browser.
    def _get_display_name(
        self,
        path: Path
    ) -> str:
        display_name = path.stem

        match = re.search(
            r"(\d{8})[_-]?(\d{6})",
            path.stem
        )

        if match is not None:
            date_text = match.group(1)
            time_text = match.group(2)

            display_name = (
                "Cap" +
                date_text[2:] +
                "T" +
                time_text
            )

        return display_name

    # ## Delete one capture MP4 and its matching JSON sidecar.
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
