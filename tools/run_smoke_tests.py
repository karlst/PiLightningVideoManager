"""
Run the SolutionFilter smoke-test corpus and report a confusion matrix.

This tool is read-only. It never moves, copies, renames, or deletes captures.

Ground truth is stored in solution_filter_smoke_tests.json. Each MP4 is labeled:

    TRUE_FLASH
    ANOMALY

The tool mirrors Analyzer classification. It loads each capture, replays
CandidateFinder at the selected High/Medium/Low sensitivity, then runs the
current SolutionFilter using that replay trigger.

All SolutionFilter rejection categories collapse to ANOMALY for the confusion
matrix. The detailed internal category and reason are shown for incorrect
results and, with -v, for every file.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# When run from source, the default smoke-test data lives under the repository
# root. When frozen by PyInstaller, __file__ points into PyInstaller's temporary
# extraction directory, so use the executable directory instead. The build
# scripts copy testData/ beside runSmokeTests in the distribution.
if getattr(sys, "frozen", False):
    APPLICATION_ROOT = Path(sys.executable).resolve().parent
    PROJECT_ROOT = APPLICATION_ROOT
else:
    PROJECT_ROOT = Path(__file__).resolve().parents[1]
    APPLICATION_ROOT = PROJECT_ROOT

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(
        0,
        str(PROJECT_ROOT),
    )

import numpy as np

from common.candidate_config import get_sensitivity_config
from video_analyzer.candidate_replay import replay_candidate_finder
from video_analyzer.capture_data import load_capture
from video_analyzer.solution_config import solution_config_for_sensitivity
from video_analyzer.solution_filter import SolutionFilter
from video_analyzer.solution_types import CATEGORY_TRUE_FLASH


EXPECTED_TRUE_FLASH = "TRUE_FLASH"
EXPECTED_ANOMALY = "ANOMALY"


@dataclass(frozen=True)
class TestResult:
    filename: str
    expected: str
    calculated: str
    correct: bool
    category: str
    reason: str


def read_manifest(
    path: Path,
) -> dict[str, str]:
    with path.open(
        "r",
        encoding="utf-8",
    ) as file:
        data = json.load(
            file
        )

    if not isinstance(
        data,
        dict,
    ):
        raise RuntimeError(
            "Smoke-test manifest must be a JSON object"
        )

    manifest: dict[str, str] = {}

    for filename, expected in data.items():
        if not isinstance(
            filename,
            str,
        ) or not isinstance(
            expected,
            str,
        ):
            raise RuntimeError(
                "Manifest filenames and classifications must be strings"
            )

        expected = (
            expected.strip().upper()
        )

        if expected not in {
            EXPECTED_TRUE_FLASH,
            EXPECTED_ANOMALY,
        }:
            raise RuntimeError(
                f"Unsupported classification for {filename}: {expected}"
            )

        manifest[
            filename
        ] = expected

    return manifest


def read_sidecar(
    path: Path,
) -> dict[str, Any]:
    with path.open(
        "r",
        encoding="utf-8",
    ) as file:
        sidecar = json.load(
            file
        )

    if not isinstance(
        sidecar,
        dict,
    ):
        raise RuntimeError(
            f"Sidecar root is not a JSON object: {path}"
        )

    return sidecar


def build_metric_arrays(
    sidecar: dict[str, Any],
) -> tuple[np.ndarray, np.ndarray]:
    records = sidecar.get(
        "frame_records",
        [],
    )

    if not isinstance(
        records,
        list,
    ) or not records:
        raise RuntimeError(
            "Sidecar contains no frame_records"
        )

    brightness_values: list[float] = []
    delta_values: list[float] = []

    for record in records:
        if not isinstance(
            record,
            dict,
        ):
            raise RuntimeError(
                "Invalid frame record"
            )

        try:
            brightness_values.append(
                float(
                    record[
                        "mean_brightness"
                    ]
                )
            )
            delta_values.append(
                float(
                    record[
                        "brightness_delta_adjacent"
                    ]
                )
            )
        except (
            KeyError,
            TypeError,
            ValueError,
        ) as error:
            raise RuntimeError(
                "Frame record is missing valid brightness metrics"
            ) from error

    return (
        np.asarray(
            brightness_values,
            dtype=np.float64,
        ),
        np.asarray(
            delta_values,
            dtype=np.float64,
        ),
    )


def get_trigger_frame_index(
    sidecar: dict[str, Any],
) -> int | None:
    candidate = sidecar.get(
        "candidate"
    )

    if isinstance(
        candidate,
        dict,
    ):
        value = candidate.get(
            "trigger_frame_index"
        )

        if value is not None:
            try:
                return int(
                    value
                )
            except (
                TypeError,
                ValueError,
            ):
                return None

        frame_number = candidate.get(
            "trigger_frame_number"
        )

        if frame_number is not None:
            try:
                return int(
                    frame_number
                ) - 1
            except (
                TypeError,
                ValueError,
            ):
                return None

    value = sidecar.get(
        "trigger_frame_index"
    )

    if value is not None:
        try:
            return int(
                value
            )
        except (
            TypeError,
            ValueError,
        ):
            return None

    frame_number = sidecar.get(
        "trigger_frame_number"
    )

    if frame_number is not None:
        try:
            return int(
                frame_number
            ) - 1
        except (
            TypeError,
            ValueError,
        ):
            return None

    return None


def get_trigger_reason(
    sidecar: dict[str, Any],
) -> str:
    candidate = sidecar.get(
        "candidate"
    )

    if isinstance(
        candidate,
        dict,
    ):
        return str(
            candidate.get(
                "trigger_reason",
                "",
            )
        )

    return str(
        sidecar.get(
            "trigger_reason",
            "",
        )
    )


def classify_capture(
    video_path: Path,
    sensitivity: str,
) -> tuple[str, str, str]:
    candidate_config = get_sensitivity_config(
        sensitivity
    )

    # Mirror Analyzer behavior exactly: load the capture, replay CandidateFinder
    # using the selected sensitivity, then feed that replay trigger into
    # SolutionFilter. Suppress normal load_capture diagnostics so the smoke-test
    # report stays readable.
    with contextlib.redirect_stdout(
        io.StringIO()
    ):
        capture_data = load_capture(
            video_path
        )

    candidate_result = replay_candidate_finder(
        capture_data,
        candidate_config,
    )

    if candidate_result.frame_index is None:
        # In the end-to-end Analyzer pipeline, "no Candidate" means the clip
        # does not survive as a flash. For this binary smoke test that maps to
        # ANOMALY. This is a correct outcome for a ground-truth anomaly and a
        # false negative for a ground-truth true flash.
        return (
            EXPECTED_ANOMALY,
            "FAILED_CANDIDATE",
            (
                f"CandidateFinder found no replay trigger at "
                f"{sensitivity} sensitivity"
            ),
        )

    solution_filter = SolutionFilter(
        solution_config_for_sensitivity(
            sensitivity
        )
    )

    result = solution_filter.evaluate(
        capture_data.pi_brightness,
        capture_data.pi_brightness_delta,
        candidate_result.frame_index,
        candidate_result.reason,
    )

    calculated = (
        EXPECTED_TRUE_FLASH
        if result.category ==
        CATEGORY_TRUE_FLASH
        else EXPECTED_ANOMALY
    )

    # Include the replay trigger in the detailed reason so an incorrect result
    # can be compared directly with Analyzer.
    reason = (
        f"Replay trigger frame "
        f"{candidate_result.frame_index + 1}: "
        f"{candidate_result.reason}; "
        f"{result.reason}"
    )

    return (
        calculated,
        result.category,
        reason,
    )


def run_one_test(
    video_path: Path,
    expected: str,
    sensitivity: str,
) -> TestResult:
    (
        calculated,
        category,
        reason,
    ) = classify_capture(
        video_path,
        sensitivity,
    )

    return TestResult(
        filename=video_path.name,
        expected=expected,
        calculated=calculated,
        correct=(
            expected ==
            calculated
        ),
        category=category,
        reason=reason,
    )


def print_confusion_matrix(
    tp: int,
    fn: int,
    fp: int,
    tn: int,
) -> None:
    print()
    print(
        "Confusion Matrix"
    )
    print()
    print(
        "                         Calculated"
    )
    print(
        "                    True Flash   Anomaly"
    )
    print(
        f"Actual True Flash   "
        f"{tp:10d}   "
        f"{fn:7d}"
    )
    print(
        f"Actual Anomaly      "
        f"{fp:10d}   "
        f"{tn:7d}"
    )
    print()
    print(
        f"TP {tp}   FN {fn}   FP {fp}   TN {tn}"
    )

    recall_denominator = (
        tp + fn
    )
    precision_denominator = (
        tp + fp
    )
    accuracy_denominator = (
        tp + fn + fp + tn
    )

    print(
        "Recall:     "
        + (
            f"{tp / recall_denominator:.1%}"
            if recall_denominator
            else "—"
        )
    )
    print(
        "Precision:  "
        + (
            f"{tp / precision_denominator:.1%}"
            if precision_denominator
            else "—"
        )
    )
    print(
        "Accuracy:   "
        + (
            f"{(tp + tn) / accuracy_denominator:.1%}"
            if accuracy_denominator
            else "—"
        )
    )


def run_tests(
    folder: Path,
    manifest_path: Path,
    sensitivity: str,
    verbosity: int,
) -> int:
    if not folder.is_dir():
        raise RuntimeError(
            f"Smoke-test folder not found: {folder}"
        )

    manifest = read_manifest(
        manifest_path
    )

    expected_true_flash = sum(
        expected ==
        EXPECTED_TRUE_FLASH
        for expected in manifest.values()
    )

    expected_anomaly = sum(
        expected ==
        EXPECTED_ANOMALY
        for expected in manifest.values()
    )

    results: list[TestResult] = []

    for filename, expected in manifest.items():
        video_path = (
            folder /
            filename
        )

        # Progress indicator: one ". " for each capture as it is opened.
        print(
            ". ",
            end="",
            flush=True,
        )

        if not video_path.is_file():
            raise RuntimeError(
                f"Smoke-test MP4 not found: {video_path}"
            )

        results.append(
            run_one_test(
                video_path,
                expected,
                sensitivity,
            )
        )

    print()

    tp = sum(
        result.expected ==
        EXPECTED_TRUE_FLASH
        and result.calculated ==
        EXPECTED_TRUE_FLASH
        for result in results
    )

    fn = sum(
        result.expected ==
        EXPECTED_TRUE_FLASH
        and result.calculated ==
        EXPECTED_ANOMALY
        for result in results
    )

    fp = sum(
        result.expected ==
        EXPECTED_ANOMALY
        and result.calculated ==
        EXPECTED_TRUE_FLASH
        for result in results
    )

    tn = sum(
        result.expected ==
        EXPECTED_ANOMALY
        and result.calculated ==
        EXPECTED_ANOMALY
        for result in results
    )

    if tp + fn != expected_true_flash:
        raise RuntimeError(
            "Internal error: True Flash row does not match manifest"
        )

    if fp + tn != expected_anomaly:
        raise RuntimeError(
            "Internal error: Anomaly row does not match manifest"
        )

    incorrect = sum(
        not result.correct
        for result in results
    )

    print(
        "SolutionFilter Smoke Test"
    )
    print(
        f"Folder:      {folder}"
    )
    print(
        f"Manifest:    {manifest_path}"
    )
    print(
        f"Sensitivity: {sensitivity}"
    )
    print(
        f"Ground truth: "
        f"{expected_true_flash} TRUE_FLASH, "
        f"{expected_anomaly} ANOMALY"
    )
    print()

    filename_width = max(
        len("File"),
        *(
            len(result.filename)
            for result in results
        ),
    )

    print(
        f"{'File':<{filename_width}}  "
        f"{'Expected':<11}  "
        f"{'Calculated':<11}  "
        f"Result"
    )
    print(
        f"{'-' * filename_width}  "
        f"{'-' * 11}  "
        f"{'-' * 11}  "
        f"{'-' * 9}"
    )

    # ----------------------------------------------------------
    # First report: compact table for every test.
    # ----------------------------------------------------------

    for result in results:
        result_text = (
            "CORRECT"
            if result.correct
            else "INCORRECT"
        )

        print(
            f"{result.filename:<{filename_width}}  "
            f"{result.expected:<11}  "
            f"{result.calculated:<11}  "
            f"{result_text}"
        )

    print()
    print(
        f"Tests: {len(results)}   "
        f"Correct: {len(results) - incorrect}   "
        f"Incorrect: {incorrect}"
    )

    # ----------------------------------------------------------
    # Second report: only incorrect classifications, with details.
    # ----------------------------------------------------------

    incorrect_results = [
        result
        for result in results
        if not result.correct
    ]

    print()
    print(
        "Incorrect Results"
    )
    print(
        "-----------------"
    )

    if not incorrect_results:
        print(
            "None."
        )
    else:
        for result in incorrect_results:
            print(
                result.filename
            )
            print(
                f"    Expected:   {result.expected}"
            )
            print(
                f"    Calculated: {result.calculated}"
            )
            print(
                f"    Category:   {result.category}"
            )
            print(
                f"    Reason:     {result.reason}"
            )
            print()

    # -v remains useful for diagnostics, but does not clutter the normal
    # report. It prints details for every correctly classified file too.
    if verbosity >= 1:
        print()
        print(
            "All Result Details"
        )
        print(
            "------------------"
        )

        for result in results:
            print(
                result.filename
            )
            print(
                f"    Expected:   {result.expected}"
            )
            print(
                f"    Calculated: {result.calculated}"
            )
            print(
                f"    Category:   {result.category}"
            )
            print(
                f"    Reason:     {result.reason}"
            )
            print()

    print_confusion_matrix(
        tp,
        fn,
        fp,
        tn,
    )

    return (
        0
        if incorrect == 0
        else 1
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run SolutionFilter smoke tests "
            "and report a confusion matrix."
        )
    )

    parser.add_argument(
        "folder",
        type=Path,
        nargs="?",
        default=None,
        help=(
            "Folder containing smoke-test MP4/JSON pairs. "
            "Default: <repository>/testData/smokeTest."
        ),
    )

    parser.add_argument(
        "--manifest",
        type=Path,
        default=None,
        help=(
            "Ground-truth JSON manifest. "
            "Default: solution_filter_smoke_tests.json "
            "in the smoke-test folder."
        ),
    )

    parser.add_argument(
        "--sensitivity",
        choices=[
            "high",
            "medium",
            "low",
        ],
        default="medium",
        help=(
            "SolutionFilter sensitivity profile. "
            "Default: medium."
        ),
    )

    parser.add_argument(
        "-v",
        "--verbosity",
        action="count",
        default=0,
        help=(
            "Show SolutionFilter category/reason for every file."
        ),
    )

    arguments = parser.parse_args()

    folder = (
        arguments.folder
        if arguments.folder is not None
        else (
            APPLICATION_ROOT
            / "testData"
            / "smokeTest"
        )
    )

    manifest_path = (
        arguments.manifest
        if arguments.manifest is not None
        else (
            folder /
            "solution_filter_smoke_tests.json"
        )
    )

    try:
        return run_tests(
            folder,
            manifest_path,
            arguments.sensitivity,
            arguments.verbosity,
        )
    except (
        OSError,
        json.JSONDecodeError,
        RuntimeError,
        ValueError,
    ) as error:
        print(
            f"Smoke test failed: {error}"
        )
        return 2


if __name__ == "__main__":
    sys.exit(
        main()
    )
