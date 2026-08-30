"""
@file capture_manager.py

@brief Manages the collection of saved MP4 captures and their JSON sidecars.

CaptureManager is the file-management layer for captures that have already
been written to disk. A capture normally consists of a matching pair of files:
an MP4 containing the video and a JSON sidecar containing the capture metadata
and analysis data.

The class scans the configured capture directory and builds the capture list
used by the web interface. While doing that it reads each JSON sidecar and
combines useful information from the MP4 file, sidecar, and filename into one
record that the browser can display.

CaptureManager also enforces the configured maximum number of saved captures.
When cleanup is required, it deletes the oldest eligible MP4 files together
with their matching JSON sidecars, while protecting captures that were saved
too recently.

This class does not create video clips or sidecars and does not decide when a
capture occurs. Those responsibilities belong to the capture pipeline. Its job
begins after capture files exist on disk: list them, describe them, and remove
old ones when necessary.
"""


from pathlib import Path
import json
import re

from video_capture.cam_config import CamConfig
from video_capture.event_log import EventLog


# ## Manages saved MP4 captures and their JSON analysis sidecars.
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

        # PI PACKAGE BROWSE FIX 2026-08-29
        # Pi SolutionFilter keeps accepted flashes in the main captures
        # directory and renames trigger_* pairs to flash_* pairs in place.
        # Browse Captures therefore reads from the main captures directory.
        self._browse_directory = (
            self._capture_directory
        )

        self._config.ensure_directories()

    # ## List captures with sidecar summary fields for the browser UI.
    def list_captures(self) -> list[dict]:
        files: list[dict] = []

        if self._browse_directory.exists():
            for path in sorted(
                self._browse_directory.glob(
                    "flash_*.mp4"
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
                        "capture_time_utc": self._get_capture_time_utc(
                            sidecar,
                            path
                        ),
                        "capture_time_display":
                            self._get_capture_time_display(
                                sidecar,
                                path
                            ),
                        "trigger_type": self._get_trigger_value(
                            sidecar,
                            "trigger_type",
                            "unknown"
                        ),
                        "trigger_display": self._get_trigger_value(
                            sidecar,
                            "trigger_display",
                            "--"
                        ),
                        "url": f"/capture_files/{path.name}",
                        "size_bytes": path.stat().st_size,
                        "modified_time": path.stat().st_mtime,
                        "capture_duration_ms":
                            self._get_capture_duration_ms(
                                sidecar
                            ),
                        "analysis": sidecar
                    }
                )

        return files

    # ## Return the directory exposed by Browse Captures playback.
    def get_capture_directory(self) -> Path:
        return self._browse_directory

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

    # ## Read a trigger field from new nested or older flat sidecars.
    def _get_trigger_value(
        self,
        sidecar: dict,
        key: str,
        default
    ):
        candidate = sidecar.get(
            "candidate"
        )

        if isinstance(
            candidate,
            dict
        ):
            return candidate.get(
                key,
                default
            )

        return sidecar.get(
            key,
            default
        )

    # ## Read clip duration from new nested or older flat sidecars.
    def _get_capture_duration_ms(
        self,
        sidecar: dict
    ):
        capture = sidecar.get(
            "capture"
        )

        if isinstance(
            capture,
            dict
        ):
            return capture.get(
                "duration_ms"
            )

        return sidecar.get(
            "capture_duration_ms"
        )

    # ## Prefer trigger UTC, then capture start UTC, then filename fallback.
    def _get_capture_time_utc(
        self,
        sidecar: dict,
        path: Path
    ) -> str:
        candidate = sidecar.get(
            "candidate",
            {}
        )

        capture = sidecar.get(
            "capture",
            {}
        )

        capture_time = ""

        if isinstance(
            candidate,
            dict
        ):
            capture_time = str(
                candidate.get(
                    "trigger_utc",
                    ""
                ) or ""
            )

        if (
            not capture_time and
            isinstance(
                capture,
                dict
            )
        ):
            capture_time = str(
                capture.get(
                    "start_utc",
                    ""
                ) or ""
            )

        if not capture_time:
            capture_time = str(
                sidecar.get(
                    "trigger_utc",
                    ""
                )
                or
                sidecar.get(
                    "capture_start_utc",
                    ""
                )
                or
                self._get_filename_time_utc(
                    path
                )
            )

        return capture_time

    # ## Return a compact readable UTC time for the capture browser.
    def _get_capture_time_display(
        self,
        sidecar: dict,
        path: Path
    ) -> str:
        capture_time = self._get_capture_time_utc(
            sidecar,
            path
        )

        display = self._format_utc_for_display(
            capture_time
        )

        return display

    # ## Build the compact display name used as a fallback capture ID.
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

    # ## Parse the older filename timestamp when no sidecar time exists.
    def _get_filename_time_utc(
        self,
        path: Path
    ) -> str:
        text = ""

        match = re.search(
            r"(\d{8})T?(\d{6})Z?",
            path.stem
        )

        if match is not None:
            date_text = match.group(1)
            time_text = match.group(2)

            text = (
                f"{date_text[0:4]}-"
                f"{date_text[4:6]}-"
                f"{date_text[6:8]}T"
                f"{time_text[0:2]}:"
                f"{time_text[2:4]}:"
                f"{time_text[4:6]}Z"
            )

        return text

    # ## Convert ISO UTC text to YYYY-MM-DD HH:MM:SS.mmm UTC.
    def _format_utc_for_display(
        self,
        value: str
    ) -> str:
        display = "--"

        if value:
            text = value.replace(
                "T",
                " "
            ).replace(
                "Z",
                ""
            )

            if "." in text:
                head, fraction = text.split(
                    ".",
                    1
                )

                text = (
                    head +
                    "." +
                    fraction[:3]
                )

            display = (
                text +
                " UTC"
            )

        return display

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
