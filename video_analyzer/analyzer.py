# ## Imports

import argparse
import json
import subprocess
import sys
from pathlib import Path

import cv2


LEFT_ARROW_KEYS = {2424832, 65361}
RIGHT_ARROW_KEYS = {2555904, 65363}
EXIT_KEYS = {ord("x"), ord("X"), 27}


# ## Read frame metadata using ffprobe

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


# ## Read a specific decoded frame

def read_frame(
    capture: cv2.VideoCapture,
    frame_number: int,
):
    capture.set(cv2.CAP_PROP_POS_FRAMES, frame_number)

    success, frame = capture.read()

    if not success:
        return None

    return frame


# ## Print information for the current frame

def print_frame_info(
    frame_number: int,
    frame_count: int,
    frame_info: list[dict],
) -> None:
    if frame_number < len(frame_info):
        info = frame_info[frame_number]
        picture_type = info.get("pict_type", "?")
        key_frame = info.get("key_frame", "?")
        timestamp = info.get("best_effort_timestamp_time", "?")
    else:
        picture_type = "?"
        key_frame = "?"
        timestamp = "?"

    print(
        f"Frame {frame_number:4d} / {frame_count - 1:4d}   "
        f"Time {timestamp:>10} s   "
        f"Type {picture_type}   "
        f"Key {key_frame}"
    )


# ## Display the current frame

def display_frame(
    capture: cv2.VideoCapture,
    frame_number: int,
    frame_count: int,
    frame_info: list[dict],
) -> bool:
    frame = read_frame(capture, frame_number)

    if frame is None:
        print(f"Unable to read frame {frame_number}.")
        return False

    cv2.imshow("Standalone Analyzer", frame)

    print_frame_info(
        frame_number,
        frame_count,
        frame_info,
    )

    return True


# ## Main program

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Step through an MP4 and display its encoded frame types."
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
        frame_info = read_frame_info(filename)
    except RuntimeError as error:
        print(f"Error: {error}")
        return 1

    capture = cv2.VideoCapture(str(filename))

    if not capture.isOpened():
        print(f"OpenCV could not open: {filename}")
        return 1

    frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = capture.get(cv2.CAP_PROP_FPS)

    print(f"File: {filename}")
    print(f"OpenCV frame count: {frame_count}")
    print(f"ffprobe frame count: {len(frame_info)}")
    print(f"Declared FPS: {fps:.3f}")
    print()
    print("Right Arrow : next frame")
    print("Left Arrow  : previous frame")
    print("X           : exit")
    print()

    frame_number = 0

    if not display_frame(
        capture,
        frame_number,
        frame_count,
        frame_info,
    ):
        capture.release()
        cv2.destroyAllWindows()
        return 1

    while True:
        key = cv2.waitKeyEx(0)

        if key in EXIT_KEYS:
            break

        if key in RIGHT_ARROW_KEYS:
            if frame_number < frame_count - 1:
                frame_number += 1
            else:
                continue

        elif key in LEFT_ARROW_KEYS:
            if frame_number > 0:
                frame_number -= 1
            else:
                continue

        else:
            continue

        display_frame(
            capture,
            frame_number,
            frame_count,
            frame_info,
        )

    capture.release()
    cv2.destroyAllWindows()

    return 0


if __name__ == "__main__":
    sys.exit(main())