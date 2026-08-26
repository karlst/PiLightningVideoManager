"""
@file clip_writer.py

@brief Encodes one fixed CameraFrame snapshot as MP4/H.264 using FFmpeg.

ClipWriter is deliberately a synchronous encoder: write_frames() does not
return until all raw BGR frames have been fed to FFmpeg and FFmpeg exits. The
separate OS process created by subprocess.Popen() does NOT make the Python call
asynchronous; writes to process.stdin and process.wait() can still occupy/block
the calling Python thread.

For automatic captures, BufferManager solves that problem by calling ClipWriter
from its dedicated CaptureWriter thread, never from CameraReader. Manual
captures may call it synchronously, and BufferManager serializes both paths.

FFmpeg tasking choices are intentionally conservative because camera acquisition
has higher priority than encoding:

- `nice -n 5` lowers the FFmpeg process CPU scheduling priority relative to the
  normal-priority camera process/thread. This is a modest bias, not CPU affinity.
- `-threads 1` asks libx264 to use one encoding thread. FFmpeg may still appear
  with several OS threads for internal I/O/framework work; the option limits the
  codec's worker threading rather than guaranteeing a one-thread process.
- No `taskset`/CPU affinity is used. Affinity experiments did not show a
  compelling advantage and unnecessarily constrain the Linux scheduler.
- `ultrafast` minimizes encoder CPU work. CRF 18 retains high image quality.

These choices came from capture-timing tests: unconstrained FFmpeg created
capture-correlated frame starvation. The present settings, combined with
BufferManager's deferred writer, substantially reduced those gaps.

ClipWriter writes video pixels only. Capture timing, trigger provenance, and
per-frame measurements belong in the JSON sidecar.
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

            # Popen creates FFmpeg as a separate OS process, but this method is
            # still synchronous: stdin.write() feeds every raw frame and wait()
            # waits for encoder completion. BufferManager therefore calls this
            # method from CaptureWriter for automatic captures.
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

    # ## Build the deliberately low-impact FFmpeg command.
    # `nice -n 5` lowers process priority; `-threads 1` limits libx264 encoder
    # workers. Do not casually remove these or add CPU affinity: these settings
    # were selected after measuring camera frame gaps while captures were saved.
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
