"""
@file camera_reader.py

@brief Camera-interface layer for the USB high-speed camera.

CameraReader is the lowest application-level interface to the physical camera.
It opens the Linux V4L2 camera device through OpenCV, requests the configured
MJPEG format, image dimensions, and frame rate, then continuously reads frames
on one dedicated Python thread.

CAMERA STREAM / THREADING MODEL

The live path is:

    USB camera
        |
        | MJPEG frames delivered by the Linux V4L2 driver
        v
    cv2.VideoCapture
        |
        | camera.read()
        | OpenCV returns one decoded image as a BGR frame
        v
    CameraReader thread
        |
        | assign sequence number and timestamps
        | construct CameraFrame
        v
    BufferManager._on_frame(camera_frame)
        |
        v
    ring buffer + trigger analysis + lightweight live processing

CameraReader owns one Python worker thread. That thread executes the complete
read/callback loop. The important consequence is that the callback is
SYNCHRONOUS: CameraReader does not call BufferManager on a second worker and
does not queue the frame for later processing. BufferManager._on_frame() must
return before this thread calls camera.read() again.

That detail is critical to capture timing. Any expensive work performed
directly or indirectly inside the callback delays the next call to
camera.read(). Earlier versions allowed MP4 encoding and sidecar work to occur
on this path, producing measurable gaps in frame timestamps. Automatic file
writing is therefore now handed off by BufferManager to a separate
CaptureWriter thread. CameraReader itself should remain as small and
predictable as possible.

camera.read() is the boundary between the Linux/OpenCV camera stream and this
application. The code requests MJPEG from the camera because the USB camera
transmits compressed frames efficiently at the required high frame rate.
OpenCV/V4L2 handles receipt of that MJPEG stream and camera.read() returns the
decoded image used by the rest of the application.

TIMESTAMP SEMANTICS

The timestamps stored in CameraFrame are taken immediately AFTER
camera.read() returns successfully. They are therefore application-side
arrival/read-completion timestamps, not hardware exposure timestamps supplied
by the camera.

timestamp_monotonic is used for elapsed-time and frame-gap calculations because
it is immune to wall-clock changes. timestamp_utc is retained for human-readable
capture metadata and correlation with external events.

The sequence number is incremented once for each successful camera.read().
Failed reads are counted separately and do not receive a CameraFrame sequence
number.

DESIGN INTENT

CameraReader should do only the work necessary to:
  * keep reading the camera continuously,
  * timestamp and number each successful frame,
  * pass the frame upward immediately.

Encoding, sidecar generation, classification, disk I/O, and other expensive
operations do not belong on this thread.
"""

from dataclasses import dataclass
from datetime import datetime
from datetime import timezone
from threading import Lock
from threading import Thread
from typing import Callable
from typing import Optional
import time

import cv2

from video_capture.cam_config import CamConfig


@dataclass
# ## Stores one captured camera frame and its timing metadata.
class CameraFrame:
    """
    @brief One captured camera frame.
    """

    sequence_number: int
    timestamp_utc: str
    timestamp_monotonic: float
    frame: object


# ## Reads camera frames continuously in a background thread.
class CameraReader:
    """
    @brief Reads camera frames continuously in a background thread.
    """

    # ## Initialize camera configuration, callback, and runtime counters.
    def __init__(
        self,
        config: CamConfig,
        on_frame: Optional[Callable[[CameraFrame], None]] = None
    ) -> None:
        self._config = config
        self._on_frame = on_frame

        self._thread: Thread | None = None
        self._stop_requested = False
        self._lock = Lock()

        self._frame_count = 0
        self._failed_read_count = 0
        self._start_time_monotonic = 0.0
        self._last_frame_time_monotonic = 0.0
        self._last_error = ""

    def start(self) -> tuple[bool, str]:
        """
        @brief Start the camera reader thread.

        @return Tuple containing success flag and status message.
        """

        success = False
        message = "CameraReader already running"

        if not self.is_running():
            with self._lock:
                self._stop_requested = False
                self._frame_count = 0
                self._failed_read_count = 0
                self._start_time_monotonic = time.monotonic()
                self._last_frame_time_monotonic = 0.0
                self._last_error = ""

            self._thread = Thread(
                target=self._run_capture_loop,
                daemon=True
            )

            self._thread.start()

            success = True
            message = "CameraReader started"

        return success, message

    def stop(self) -> tuple[bool, str]:
        """
        @brief Stop the camera reader thread.

        @return Tuple containing success flag and status message.
        """

        success = False
        message = "CameraReader was not running"

        if self.is_running():
            with self._lock:
                self._stop_requested = True

            if self._thread is not None:
                self._thread.join(
                    timeout=5.0
                )

            self._thread = None

            success = True
            message = "CameraReader stopped"

        return success, message

    def is_running(self) -> bool:
        """
        @brief Determine whether the reader thread is running.

        @return True if running, otherwise False.
        """

        running = False

        if self._thread is not None:
            running = self._thread.is_alive()

        return running

    def get_status(self) -> dict:
        """
        @brief Return current reader status.

        @return Dictionary containing runtime counters and estimated FPS.
        """

        now = time.monotonic()

        with self._lock:
            frame_count = self._frame_count
            failed_read_count = self._failed_read_count
            start_time = self._start_time_monotonic
            last_frame_time = self._last_frame_time_monotonic
            last_error = self._last_error

        elapsed_seconds = 0.0
        estimated_fps = 0.0
        seconds_since_last_frame = None

        if start_time > 0.0:
            elapsed_seconds = now - start_time

        if elapsed_seconds > 0.0:
            estimated_fps = frame_count / elapsed_seconds

        if last_frame_time > 0.0:
            seconds_since_last_frame = now - last_frame_time

        status = {
            "running": self.is_running(),
            "frame_count": frame_count,
            "failed_read_count": failed_read_count,
            "elapsed_seconds": elapsed_seconds,
            "estimated_fps": estimated_fps,
            "seconds_since_last_frame": seconds_since_last_frame,
            "last_error": last_error
        }

        return status

    # ## Run the camera open/read/release lifecycle inside the worker thread.
    def _run_capture_loop(self) -> None:
        camera = None

        try:
            camera = self._open_camera()

            if camera is None:
                self._set_error(
                    "Failed to open camera"
                )
            else:
                self._capture_frames(
                    camera
                )

        except Exception as error:
            self._set_error(
                str(error)
            )

        finally:
            if camera is not None:
                camera.release()

    # ## Open and configure the V4L2 camera device.
    def _open_camera(self):
        camera = cv2.VideoCapture(
            self._config.video_device,
            cv2.CAP_V4L2
        )

        camera.set(
            cv2.CAP_PROP_FOURCC,
            cv2.VideoWriter_fourcc(
                "M",
                "J",
                "P",
                "G"
            )
        )

        camera.set(
            cv2.CAP_PROP_FRAME_WIDTH,
            self._config.frame_width_pixels
        )

        camera.set(
            cv2.CAP_PROP_FRAME_HEIGHT,
            self._config.frame_height_pixels
        )

        camera.set(
            cv2.CAP_PROP_FPS,
            self._config.frame_rate_fps
        )

        if not camera.isOpened():
            camera.release()
            camera = None

        return camera

    # ## Read frames until stop is requested.
    #
    # This loop is the application's live camera stream. It runs entirely on
    # the CameraReader worker thread. After each successful camera.read(), the
    # frame is passed synchronously to _handle_frame(), which in turn invokes
    # BufferManager's callback. The next camera.read() does not occur until
    # that callback returns, so callback latency directly affects how quickly
    # the application gets back to the camera.
    def _capture_frames(
        self,
        camera
    ) -> None:
        while not self._is_stop_requested():
            success, frame = camera.read()

            if success:
                self._handle_frame(
                    frame
                )
            else:
                self._record_failed_read()
                time.sleep(
                    0.001
                )

    # ## Timestamp one frame and deliver it to the frame callback.
    #
    # The timestamps describe when this application received/completed the
    # read of the frame; they are not exposure timestamps from camera hardware.
    # The callback is executed inline on the CameraReader thread.
    def _handle_frame(
        self,
        frame
    ) -> None:
        timestamp_monotonic = time.monotonic()

        timestamp_utc = datetime.now(
            timezone.utc
        ).strftime(
            "%Y-%m-%dT%H:%M:%S.%fZ"
        )

        with self._lock:
            self._frame_count += 1
            sequence_number = self._frame_count
            self._last_frame_time_monotonic = timestamp_monotonic

        camera_frame = CameraFrame(
            sequence_number=sequence_number,
            timestamp_utc=timestamp_utc,
            timestamp_monotonic=timestamp_monotonic,
            frame=frame
        )

        if self._on_frame is not None:
            self._on_frame(
                camera_frame
            )

    # ## Increment the failed read counter.
    def _record_failed_read(self) -> None:
        with self._lock:
            self._failed_read_count += 1

    # ## Store the latest camera error message.
    def _set_error(
        self,
        message: str
    ) -> None:
        with self._lock:
            self._last_error = message

    # ## Read the stop flag under lock.
    def _is_stop_requested(self) -> bool:
        stop_requested = False

        with self._lock:
            stop_requested = self._stop_requested

        return stop_requested