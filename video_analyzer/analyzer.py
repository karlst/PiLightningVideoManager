"""Entry point for the desktop video analyzer."""

import argparse
from pathlib import Path
import sys

from PySide6.QtWidgets import QApplication

from common.candidate_config import CANDIDATE_CONFIG
from video_analyzer.analyzer_window import AnalyzerWindow
from video_analyzer.candidate_replay import replay_candidate_finder
from video_analyzer.capture_data import load_capture


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Inspect a capture frame-by-frame with "
            "sidecar data and brightness graphs."
        )
    )

    parser.add_argument(
        "capture",
        type=Path,
        help=(
            "Capture basename, MP4 filename, "
            "or JSON sidecar filename"
        ),
    )

    arguments = parser.parse_args()

    try:
        capture_data = load_capture(
            arguments.capture
        )

        candidate_result = replay_candidate_finder(
            capture_data.sidecar,
            CANDIDATE_CONFIG,
        )

        application = QApplication(sys.argv)

        window = AnalyzerWindow(
            capture_data=capture_data,
            candidate_result=candidate_result,
        )

        window.show()

        return application.exec()

    except RuntimeError as error:
        print(f"Error: {error}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
