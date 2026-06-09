"""
@file clip_writer.py

@brief Writes buffered camera frames to one MP4/H.264 file using FFmpeg.
"""

from datetime import datetime
from datetime import timezone
from pathlib import Path
import subprocess

import numpy as np

from camera_reader import CameraFrame


class ClipWriter:
    """
    @brief Writes buffered OpenCV frames to an MP4/H.264 video file.
    """

    def __init__(
        self,
        output_directory: Path,
        frame_rate_fps: int,
        ffmpeg_path: str = "ffmpeg"
    ) -> None:
        self._output_directory = output_directory
        self._frame_rate_fps = frame_rate_fps
        self._ffmpeg_path = ffmpeg_path

    def write_frames(
        self,
        frames: list[CameraFrame]
    ) -> tuple[bool, str, dict]:
        success = False
        message = "No frames to write"

        status = {
            "output_file": "",
            "frames_requested": len(frames),
            "frames_written": 0,
            "codec": "libx264",
            "container": "mp4",
            "ffmpeg_return_code": None,
            "ffmpeg_error": ""
        }

        if len(frames) > 0:
            self._output_directory.mkdir(
                parents=True,
                exist_ok=True
            )

            output_file = (
                self._output_directory /
                self._create_clip_filename()
            )

            first_frame = frames[0].frame

            frame_height_pixels = int(
                first_frame.shape[0]
            )

            frame_width_pixels = int(
                first_frame.shape[1]
            )

            process = subprocess.Popen(
                self._create_ffmpeg_command(
                    output_file=output_file,
                    frame_width_pixels=frame_width_pixels,
                    frame_height_pixels=frame_height_pixels
                ),
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE
            )

            frames_written = 0
            ffmpeg_error = ""

            try:
                if process.stdin is not None:
                    for camera_frame in frames:
                        frame = camera_frame.frame

                        frame_height = int(
                            frame.shape[0]
                        )

                        frame_width = int(
                            frame.shape[1]
                        )

                        if (
                            frame_width == frame_width_pixels and
                            frame_height == frame_height_pixels
                        ):
                            contiguous_frame = np.ascontiguousarray(
                                frame
                            )

                            process.stdin.write(
                                contiguous_frame.tobytes()
                            )

                            frames_written += 1

                    process.stdin.close()

                if process.stderr is not None:
                    ffmpeg_error = (
                        process.stderr.read()
                        .decode(
                            "utf-8",
                            errors="replace"
                        )
                    )

                return_code = process.wait()

                success = (
                    return_code == 0 and
                    frames_written == len(frames)
                )

                if success:
                    message = (
                        f"ClipWriter wrote {frames_written} "
                        f"of {len(frames)} frames to MP4/H.264"
                    )
                else:
                    message = (
                        f"ClipWriter failed: wrote {frames_written} "
                        f"of {len(frames)} frames"
                    )

                status = {
                    "output_file": str(output_file),
                    "frames_requested": len(frames),
                    "frames_written": frames_written,
                    "codec": "libx264",
                    "container": "mp4",
                    "ffmpeg_return_code": return_code,
                    "ffmpeg_error": ffmpeg_error[-1000:]
                }

            except Exception as exception:
                try:
                    process.kill()
                except Exception:
                    pass

                message = (
                    f"ClipWriter exception: {exception}"
                )

                status = {
                    "output_file": str(output_file),
                    "frames_requested": len(frames),
                    "frames_written": frames_written,
                    "codec": "libx264",
                    "container": "mp4",
                    "ffmpeg_return_code": None,
                    "ffmpeg_error": str(exception)
                }

        return success, message, status

    def _create_ffmpeg_command(
        self,
        output_file: Path,
        frame_width_pixels: int,
        frame_height_pixels: int
    ) -> list[str]:
        command = [
            self._ffmpeg_path,
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",

            "-f",
            "rawvideo",
            "-pix_fmt",
            "bgr24",
            "-s",
            (
                f"{frame_width_pixels}"
                f"x{frame_height_pixels}"
            ),
            "-r",
            str(self._frame_rate_fps),
            "-i",
            "pipe:0",

            "-an",
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-crf",
            "18",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",

            str(output_file)
        ]

        return command

    def _create_clip_filename(self) -> str:
        filename = datetime.now(
            timezone.utc
        ).strftime(
            "trigger_%Y%m%dT%H%M%SZ.mp4"
        )

        return filename