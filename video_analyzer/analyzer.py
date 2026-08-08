"""Entry point for the desktop video analyzer."""

import argparse
from pathlib import Path
import sys

from PySide6.QtWidgets import QApplication

from video_analyzer.analyzer_window import AnalyzerWindow
from video_analyzer.candidate_replay import replay_candidate_finder
from video_analyzer.capture_data import load_capture
from video_analyzer.solution_filter import SolutionFilter


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

        # Replay starts with the exact CandidateConfig recorded by the Pi.
        # The analyzer may later modify a separate replay config interactively.
        replay_config = (
            capture_data.capture_candidate_config
        )

        candidate_result = replay_candidate_finder(
            capture_data.sidecar,
            replay_config,
        )

        solution_filter = SolutionFilter()
        solution_result = solution_filter.evaluate(
            capture_data.pi_brightness,
            capture_data.pi_brightness_delta,
            capture_data.original_trigger_frame_index,
        )

        application = QApplication(sys.argv)

        window = AnalyzerWindow(
            capture_data=capture_data,
            candidate_result=candidate_result,
            solution_result=solution_result,
            initial_candidate_config=replay_config,
        )

        window.show()

        return application.exec()

    except RuntimeError as error:
        print(f"Error: {error}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
