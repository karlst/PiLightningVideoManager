"""
Desktop Video Analyzer program entry point.

This module is intentionally small. It parses the initial capture filename
supplied on the command line, loads the MP4/JSON capture pair, replays
CandidateFinder against the archived metrics, runs the desktop-only
SolutionFilter, then starts the Qt graphical application and creates
AnalyzerWindow. Once running, AnalyzerWindow can load additional MP4 captures
through File -> Open without restarting the application.

Keeping startup here and most GUI behavior in AnalyzerWindow makes the program
easier to package and keeps command-line/error handling separate from the user
interface.
"""

import argparse
from pathlib import Path
import sys

from PySide6.QtWidgets import QApplication

from common.candidate_config import CANDIDATE_CONFIG
from video_analyzer.analyzer_window import AnalyzerWindow
from video_analyzer.candidate_replay import replay_candidate_finder
from video_analyzer.capture_data import load_capture
from video_analyzer.solution_config import SOLUTION_CONFIG
from video_analyzer.solution_filter import SolutionFilter
from video_analyzer.solution_filter import failed_candidate_result

# ## Parse the optional startup path and start the Qt event loop.
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
        nargs="?",
        default=None,
        help=(
            "Optional MP4/JSON capture or folder. "
            "If omitted, Vfa opens the capture browser "
            "in the current directory."
        ),
    )

    arguments = parser.parse_args()

    application = QApplication(sys.argv)

    startup_path = (
        arguments.capture
        if arguments.capture is not None
        else Path.cwd()
    )

    try:
        if startup_path.is_dir():
            window = AnalyzerWindow(
                initial_directory=startup_path,
            )
        else:
            capture_data = load_capture(
                startup_path
            )

            candidate_result = replay_candidate_finder(
                capture_data,
                CANDIDATE_CONFIG,
            )

            if candidate_result.frame_index is None:
                solution_result = failed_candidate_result()
            else:
                solution_filter = SolutionFilter(
                    SOLUTION_CONFIG
                )
                solution_result = solution_filter.evaluate(
                    capture_data.pi_brightness,
                    capture_data.pi_brightness_delta,
                    candidate_result.frame_index,
                    candidate_result.reason,
                )

            window = AnalyzerWindow(
                capture_data=capture_data,
                candidate_result=candidate_result,
                solution_result=solution_result,
            )

        window.show()
        return application.exec()

    except RuntimeError as error:
        print(f"Error: {error}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
