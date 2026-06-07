"""
@file clip_writer.py

@brief Writes buffered camera frames to disk.
"""

from datetime import datetime
from datetime import timezone
from pathlib import Path

import cv2

from camera_reader import CameraFrame


class ClipWriter:
    """
    @brief Writes captured frame snapshots to disk.
    """

    def __init__(
        self,
        output_directory: Path
    ) -> None:
        self._output_directory = output_directory

    def write_frames(
        self,
        frames: list[CameraFrame]
    ) -> tuple[bool, str, dict]:
        success = False
        message = "No frames to write"

        status = {
            "output_directory": "",
            "frames_requested": len(
                frames
            ),
            "frames_written": 0
        }

        if len(frames) > 0:
            clip_directory = (
                self._output_directory /
                self._create_clip_directory_name()
            )

            clip_directory.mkdir(
                parents=True,
                exist_ok=True
            )

            frames_written = 0

            for iFrame, camera_frame in enumerate(
                frames
            ):
                output_file = (
                    clip_directory /
                    (
                        f"frame_{iFrame:06d}"
                        f"_seq_{camera_frame.sequence_number:08d}.jpg"
                    )
                )

                write_success = cv2.imwrite(
                    str(output_file),
                    camera_frame.frame
                )

                if write_success:
                    frames_written += 1

            success = (
                frames_written == len(
                    frames
                )
            )

            message = (
                f"ClipWriter wrote {frames_written} "
                f"of {len(frames)} frames"
            )

            status = {
                "output_directory": str(
                    clip_directory
                ),
                "frames_requested": len(
                    frames
                ),
                "frames_written": frames_written
            }

        return success, message, status

    def _create_clip_directory_name(self) -> str:
        directory_name = datetime.now(
            timezone.utc
        ).strftime(
            "trigger_%Y%m%dT%H%M%SZ"
        )

        return directory_name