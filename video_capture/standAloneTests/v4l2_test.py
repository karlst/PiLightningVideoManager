"""
@file v4l2_test.py

@brief Standalone V4L2/OpenCV camera capture test.

Purpose:
    Verify that the ELP USB camera can be accessed through
    V4L2/OpenCV and sustain the target capture rate of
    approximately 260 FPS at 640x360 MJPEG.

Behavior:
    - Opens /dev/video0 using the V4L2 backend.
    - Configures MJPEG, 640x360, 260 FPS.
    - Continuously captures frames.
    - Reports measured FPS once per second.
    - Saves the first five frames as JPEG images.
    - Exits on Ctrl-C.

This program is intentionally independent of the Flask web
application, CameraReader, BufferManager, and future frame
analysis code. It serves as a hardware and software
verification tool.

Expected Result:
    Sustained capture rate near 260 FPS.

Author:
    Karl Stock
"""

import time
from pathlib import Path

import cv2


def main() -> int:
    return_code = 0

    output_dir = Path.home() / "Documents" / "videoManager" / "v4l2_test"
    output_dir.mkdir(
        parents=True,
        exist_ok=True
    )

    camera = cv2.VideoCapture(
        "/dev/video0",
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
        640
    )

    camera.set(
        cv2.CAP_PROP_FRAME_HEIGHT,
        360
    )

    camera.set(
        cv2.CAP_PROP_FPS,
        260
    )

    if not camera.isOpened():
        print("Failed to open /dev/video0")
        return_code = 1
    else:
        frame_count = 0
        saved_count = 0
        start_time = time.monotonic()
        last_report_time = start_time
        last_report_frame_count = 0

        print("Started V4L2 OpenCV capture test")
        print("Press Ctrl-C to stop")

        try:
            while True:
                success, frame = camera.read()

                if success:
                    frame_count += 1

                    if saved_count < 5:
                        output_file = output_dir / f"frame_{saved_count:04d}.jpg"

                        cv2.imwrite(
                            str(output_file),
                            frame
                        )

                        saved_count += 1

                    now = time.monotonic()

                    if now - last_report_time >= 1.0:
                        interval_seconds = now - last_report_time
                        interval_frames = frame_count - last_report_frame_count
                        interval_fps = interval_frames / interval_seconds
                        total_fps = frame_count / (now - start_time)

                        print(
                            f"frames={frame_count} "
                            f"interval_fps={interval_fps:.1f} "
                            f"total_fps={total_fps:.1f}"
                        )

                        last_report_time = now
                        last_report_frame_count = frame_count
                else:
                    print("Frame read failed")
                    time.sleep(
                        0.01
                    )

        except KeyboardInterrupt:
            print("Stopping")

        finally:
            camera.release()

            elapsed_seconds = time.monotonic() - start_time

            if elapsed_seconds > 0:
                print(
                    f"Final frames={frame_count} "
                    f"elapsed={elapsed_seconds:.2f} "
                    f"fps={frame_count / elapsed_seconds:.1f}"
                )

    return return_code


if __name__ == "__main__":
    exit(
        main()
    )
