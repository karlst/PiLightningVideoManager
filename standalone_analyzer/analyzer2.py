# ## Imports

import argparse
import json
import subprocess
import sys
from pathlib import Path

import cv2
import matplotlib.pyplot as plt
import numpy as np


# ## Read encoded-frame metadata with ffprobe

def read_frame_info(filename: Path) -> list[dict]:
    command = [
        "ffprobe",
        "-v", "error",
        "-select_streams", "v:0",
        "-show_frames",
        "-show_entries",
        "frame=pict_type,key_frame,best_effort_timestamp_time",
        "-of", "json",
        str(filename),
    ]

    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=True,
        )
    except FileNotFoundError:
        raise RuntimeError("ffprobe was not found in PATH.") from None
    except subprocess.CalledProcessError as error:
        message = error.stderr.strip() or "ffprobe failed."
        raise RuntimeError(message) from error

    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise RuntimeError("ffprobe returned invalid JSON.") from error

    frames = data.get("frames", [])

    if not frames:
        raise RuntimeError("ffprobe found no video frames.")

    return frames


# ## Analyze every frame in the clip

def analyze_clip(filename: Path) -> tuple[np.ndarray, np.ndarray]:
    capture = cv2.VideoCapture(str(filename))

    if not capture.isOpened():
        raise RuntimeError(f"OpenCV could not open: {filename}")

    brightness_values: list[float] = []

    while True:
        success, frame = capture.read()

        if not success:
            break

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        brightness_values.append(float(gray.mean()))

    capture.release()

    if not brightness_values:
        raise RuntimeError("OpenCV decoded no video frames.")

    brightness = np.asarray(brightness_values, dtype=np.float64)

    brightness_delta = np.zeros_like(brightness)
    brightness_delta[1:] = brightness[1:] - brightness[:-1]

    return brightness, brightness_delta


# ## Interactive analyzer display

class AnalyzerDisplay:

    # ## Initialize display

    def __init__(
        self,
        filename: Path,
        frame_info: list[dict],
        brightness: np.ndarray,
        brightness_delta: np.ndarray,
    ) -> None:
        self.filename = filename
        self.frame_info = frame_info
        self.brightness = brightness
        self.brightness_delta = brightness_delta
        self.frame_count = len(brightness)
        self.frame_number = 0

        self.capture = cv2.VideoCapture(str(filename))

        if not self.capture.isOpened():
            raise RuntimeError(f"OpenCV could not reopen: {filename}")

        self.metrics = [
            ("Absolute brightness", self.brightness),
            ("Brightness change", self.brightness_delta),
        ]

        self.figure = plt.figure(
            num="Standalone Analyzer",
            figsize=(12, 9),
        )

        grid = self.figure.add_gridspec(
            nrows=1 + len(self.metrics),
            ncols=1,
            height_ratios=[3, *([1] * len(self.metrics))],
            hspace=0.12,
        )

        self.image_axis = self.figure.add_subplot(grid[0])

        self.graph_axes = []
        self.cursor_lines = []

        shared_axis = None

        for index, (title, values) in enumerate(self.metrics):
            axis = self.figure.add_subplot(
                grid[index + 1],
                sharex=shared_axis,
            )

            if shared_axis is None:
                shared_axis = axis

            axis.plot(np.arange(self.frame_count), values)
            axis.set_ylabel(title)
            axis.grid(True)

            cursor = axis.axvline(
                self.frame_number,
                linestyle="--",
            )

            self.graph_axes.append(axis)
            self.cursor_lines.append(cursor)

        for axis in self.graph_axes[:-1]:
            axis.tick_params(labelbottom=False)

        self.graph_axes[-1].set_xlabel("Frame number")
        self.graph_axes[-1].set_xlim(0, max(1, self.frame_count - 1))

        self.image_artist = None

        self.figure.canvas.mpl_connect(
            "key_press_event",
            self.on_key_press,
        )

        self.figure.canvas.mpl_connect(
            "close_event",
            self.on_close,
        )

        self.update_display()

    # ## Read a specific decoded frame

    def read_frame(self, frame_number: int):
        self.capture.set(
            cv2.CAP_PROP_POS_FRAMES,
            frame_number,
        )

        success, frame = self.capture.read()

        if not success:
            return None

        return cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

    # ## Get encoded metadata for current frame

    def get_current_frame_info(self) -> tuple[str, str, str]:
        if self.frame_number >= len(self.frame_info):
            return "?", "?", "?"

        info = self.frame_info[self.frame_number]

        picture_type = str(info.get("pict_type", "?"))
        key_frame = str(info.get("key_frame", "?"))
        timestamp = str(
            info.get("best_effort_timestamp_time", "?")
        )

        return picture_type, key_frame, timestamp

    # ## Update image, title, and graph cursors

    def update_display(self) -> None:
        frame = self.read_frame(self.frame_number)

        if frame is None:
            print(f"Unable to read frame {self.frame_number}.")
            return

        if self.image_artist is None:
            self.image_artist = self.image_axis.imshow(frame)
            self.image_axis.axis("off")
        else:
            self.image_artist.set_data(frame)

        picture_type, key_frame, timestamp = (
            self.get_current_frame_info()
        )

        brightness = self.brightness[self.frame_number]
        brightness_delta = self.brightness_delta[
            self.frame_number
        ]

        self.image_axis.set_title(
            f"{self.filename.name}    "
            f"Frame {self.frame_number} / {self.frame_count - 1}    "
            f"Time {timestamp} s    "
            f"Type {picture_type}    "
            f"Key {key_frame}"
        )

        for cursor in self.cursor_lines:
            cursor.set_xdata(
                [self.frame_number, self.frame_number]
            )

        print(
            f"Frame {self.frame_number:4d} / "
            f"{self.frame_count - 1:4d}   "
            f"Time {timestamp:>10} s   "
            f"Type {picture_type}   "
            f"Key {key_frame}   "
            f"Brightness {brightness:8.3f}   "
            f"Delta {brightness_delta:+8.3f}"
        )

        self.figure.canvas.draw_idle()

    # ## Handle keyboard input

    def on_key_press(self, event) -> None:
        if event.key == "right":
            if self.frame_number < self.frame_count - 1:
                self.frame_number += 1
                self.update_display()

        elif event.key == "left":
            if self.frame_number > 0:
                self.frame_number -= 1
                self.update_display()

        elif event.key in {"x", "X", "escape"}:
            plt.close(self.figure)

    # ## Release resources when window closes

    def on_close(self, _event) -> None:
        if self.capture is not None:
            self.capture.release()
            self.capture = None

    # ## Run interactive display

    def run(self) -> None:
        print()
        print("Right Arrow : next frame")
        print("Left Arrow  : previous frame")
        print("X           : exit")
        print()

        plt.show()


# ## Main program

def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Display an MP4 frame-by-frame with frame metadata "
            "and brightness graphs."
        )
    )

    parser.add_argument(
        "filename",
        type=Path,
        help="MP4 file to examine",
    )

    arguments = parser.parse_args()
    filename = arguments.filename

    if not filename.is_file():
        print(f"File not found: {filename}")
        return 1

    try:
        print("Reading ffprobe frame metadata...")
        frame_info = read_frame_info(filename)

        print("Analyzing clip brightness...")
        brightness, brightness_delta = analyze_clip(filename)

        print(f"File: {filename}")
        print(f"Decoded frames: {len(brightness)}")
        print(f"ffprobe frames: {len(frame_info)}")

        display = AnalyzerDisplay(
            filename,
            frame_info,
            brightness,
            brightness_delta,
        )

        display.run()

    except RuntimeError as error:
        print(f"Error: {error}")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())