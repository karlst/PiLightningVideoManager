"""
@file clip_writer.py

@brief Writes buffered camera frames to one MP4/H.264 file using FFmpeg.

ClipWriter is the final video-output stage of the buffered capture pipeline.
BufferManager keeps recent CameraFrame objects in memory. When a manual or
automatic capture is saved, BufferManager passes a snapshot of those frames to
ClipWriter.

The frames held in memory are OpenCV BGR images, not an already encoded video
stream. ClipWriter starts an FFmpeg process and writes the raw BGR pixel bytes
to FFmpeg through standard input. FFmpeg then encodes those frames as H.264
video inside an MP4 container.

ClipWriter writes only the video pixels. Per-frame timing, trigger information,
camera metadata, and analysis measurements are stored separately in the JSON
sidecar written by SidecarWriter.

This class does not read directly from the camera and does not decide when a
capture should occur; CameraReader and BufferManager handle those jobs.
"""

from datetime import datetime
from datetime import timezone
from pathlib import Path
import subprocess

import numpy as np

from video_capture.camera_reader import CameraFrame


# ## Writes buffered OpenCV frames to an MP4/H.264 video file.
class ClipWriter:
    """
    @brief Writes buffered OpenCV frames to an MP4/H.264 video file.
    """

    # ## Initialize the writer output location, frame rate, and FFmpeg path.
    def __init__(
        self,
        output_directory: Path,
        frame_rate_fps: int,
        ffmpeg_path: str = "ffmpeg"
    ) -> None:
        self._output_directory = output_directory
        self._frame_rate_fps = frame_rate_fps
        self._ffmpeg_path = ffmpeg_path

    # ## Write a list of CameraFrame objects to one MP4 file.
    def write_frames(
        self,
        frames: list[CameraFrame]
    ) -> tuple[bool, str, dict]:
        success = False
        message = "No frames to write"

        status = {
            "output_file": "",
            "saved_utc": "",
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

            saved_utc = self._get_now_utc_text()

            output_file = (
                self._output_directory /
                self._create_clip_filename(
                    saved_utc
                )
            )

            first_frame = frames[0].frame

            frame_height_pixels = int(
                first_frame.shape[0]
            )

            frame_width_pixels = int(
                first_frame.shape[1]
            )

            # Feed raw BGR frames to FFmpeg through stdin. The MP4 carries
            # pixels only; detailed frame timing stays in the JSON sidecar.
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
                    "saved_utc": saved_utc,
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
                    "saved_utc": saved_utc,
                    "frames_requested": len(frames),
                    "frames_written": frames_written,
                    "codec": "libx264",
                    "container": "mp4",
                    "ffmpeg_return_code": None,
                    "ffmpeg_error": str(exception)
                }

        return success, message, status

    # ## Build the FFmpeg command used to encode raw BGR frames.
    def _create_ffmpeg_command(
        self,
        output_file: Path,
        frame_width_pixels: int,
        frame_height_pixels: int
    ) -> list[str]:
        command = [
             "nice",
            "-n",
            "5",
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
            "-threads",
             "1",
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

    # ## Create a filename from the save time, not from frame time.
    def _create_clip_filename(
        self,
        saved_utc: str
    ) -> str:
        filename_time = datetime.fromisoformat(
            saved_utc.replace(
                "Z",
                "+00:00"
            )
        )

        filename = filename_time.strftime(
            "trigger_%Y%m%dT%H%M%SZ.mp4"
        )

        return filename

    # ## Return UTC with millisecond precision for capture-save metadata.
    def _get_now_utc_text(self) -> str:
        now_utc = datetime.now(
            timezone.utc
        )

        text = now_utc.isoformat(
            timespec="milliseconds"
        ).replace(
            "+00:00",
            "Z"
        )

        return text
