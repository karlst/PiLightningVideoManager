"""
Run the frozen production-classifier smoke-test corpus and report a confusion matrix.

This tool is read-only. It never moves, copies, renames, or deletes captures.

Ground truth is stored in solution_filter_smoke_tests.json. Existing manifests
may label flashes as TRUE_FLASH; that legacy label is accepted and normalized
to the V8 production label FLASH. ANOMALY remains ANOMALY.

IMPORTANT:
    This smoke test exercises the same classifier inputs used in production:

        saved sidecar brightness arrays
        + saved Pi trigger frame
        -> frozen logistic-regression classifier
        -> FLASH / ANOMALY + class confidence

    It deliberately does NOT decode the MP4 or rerun CandidateFinder. Replaying
    an MP4 can produce different brightness values or a different trigger frame,
    which would test a different input path than the one used to train and
    validate the classifier.

The sidecar reader in this test intentionally accepts both pre-V8 and V8
sidecars so the classifier can be smoke-tested before the V7 -> V8 migration.
It reads only the recorded frame metrics and trigger location needed by the
classifier; it does not normalize or rewrite the sidecar.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np


# When run from source, the default smoke-test data lives under the repository
# root. When frozen by PyInstaller, __file__ points into PyInstaller's temporary
# extraction directory, so use the executable directory instead.
if getattr(sys, "frozen", False):
    APPLICATION_ROOT = Path(sys.executable).resolve().parent
    PROJECT_ROOT = APPLICATION_ROOT
else:
    PROJECT_ROOT = Path(__file__).resolve().parents[1]
    APPLICATION_ROOT = PROJECT_ROOT

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from common.classification_model import (
    CLASSIFICATION_ANOMALY,
    CLASSIFICATION_FLASH,
    classify_arrays,
)


EXPECTED_FLASH = CLASSIFICATION_FLASH
EXPECTED_ANOMALY = CLASSIFICATION_ANOMALY
LEGACY_EXPECTED_FLASH = "TRUE_FLASH"
LEGACY_EXPECTED_TF = "TF"


@dataclass(frozen=True)
class TestResult:
    filename: str
    expected: str
    calculated: str
    correct: bool
    confidence: float
    trigger_frame_index: int
    reason: str


def read_manifest(path: Path) -> dict[str, str]:
    with path.open("r", encoding="utf-8") as file:
        data = json.load(file)

    if not isinstance(data, dict):
        raise RuntimeError("Smoke-test manifest must be a JSON object")

    manifest: dict[str, str] = {}

    for filename, expected in data.items():
        if not isinstance(filename, str) or not isinstance(expected, str):
            raise RuntimeError(
                "Manifest filenames and classifications must be strings"
            )

        expected = expected.strip().upper()

        if expected in {LEGACY_EXPECTED_FLASH, LEGACY_EXPECTED_TF}:
            expected = EXPECTED_FLASH

        if expected not in {EXPECTED_FLASH, EXPECTED_ANOMALY}:
            raise RuntimeError(
                f"Unsupported classification for {filename}: {expected}"
            )

        manifest[filename] = expected

    return manifest


def read_classifier_inputs(
    sidecar_path: Path,
) -> tuple[np.ndarray, np.ndarray, int]:
    """Read only the classifier inputs from either a legacy or V8 sidecar."""
    with sidecar_path.open("r", encoding="utf-8") as file:
        sidecar = json.load(file)

    if not isinstance(sidecar, dict):
        raise RuntimeError("Sidecar root must be a JSON object")

    records = sidecar.get("frame_records")
    if not isinstance(records, list) or not records:
        raise RuntimeError("Sidecar contains no frame_records")

    brightness_values: list[float] = []
    delta_values: list[float] = []

    for record in records:
        if not isinstance(record, dict):
            raise RuntimeError("Invalid frame record")

        try:
            brightness_values.append(float(record["mean_brightness"]))
            delta_values.append(float(record["brightness_delta_adjacent"]))
        except (KeyError, TypeError, ValueError) as error:
            raise RuntimeError(
                "Frame record is missing valid brightness metrics"
            ) from error

    trigger_frame_index: int | None = None

    candidate = sidecar.get("candidate")
    if isinstance(candidate, dict):
        value = candidate.get("trigger_frame_index")
        if value is not None:
            try:
                trigger_frame_index = int(value)
            except (TypeError, ValueError):
                trigger_frame_index = None

        if trigger_frame_index is None:
            value = candidate.get("trigger_frame_number")
            if value is not None:
                try:
                    trigger_frame_index = int(value) - 1
                except (TypeError, ValueError):
                    trigger_frame_index = None

    if trigger_frame_index is None:
        value = sidecar.get("trigger_frame_index")
        if value is not None:
            try:
                trigger_frame_index = int(value)
            except (TypeError, ValueError):
                trigger_frame_index = None

    if trigger_frame_index is None:
        value = sidecar.get("trigger_frame_number")
        if value is not None:
            try:
                trigger_frame_index = int(value) - 1
            except (TypeError, ValueError):
                trigger_frame_index = None

    if trigger_frame_index is None:
        raise RuntimeError("Sidecar contains no valid recorded Pi trigger frame")

    if not 0 <= trigger_frame_index < len(brightness_values):
        raise RuntimeError(
            f"Recorded trigger frame {trigger_frame_index} is outside "
            f"{len(brightness_values)} frame records"
        )

    return (
        np.asarray(brightness_values, dtype=np.float64),
        np.asarray(delta_values, dtype=np.float64),
        trigger_frame_index,
    )


def classify_capture(video_path: Path) -> tuple[str, float, int, str]:
    sidecar_path = video_path.with_suffix(".json")

    if not sidecar_path.is_file():
        raise RuntimeError(f"Matching JSON sidecar not found: {sidecar_path}")

    brightness, brightness_delta, trigger_frame_index = read_classifier_inputs(
        sidecar_path
    )

    result = classify_arrays(
        brightness,
        brightness_delta,
        trigger_frame_index,
    )

    return (
        result.classification,
        (
            result.flash_probability
            if result.classification == EXPECTED_FLASH
            else 1.0 - result.flash_probability
        ),
        trigger_frame_index,
        result.reason,
    )


def run_one_test(video_path: Path, expected: str) -> TestResult:
    calculated, confidence, trigger_frame_index, reason = classify_capture(video_path)

    return TestResult(
        filename=video_path.name,
        expected=expected,
        calculated=calculated,
        correct=(expected == calculated),
        confidence=confidence,
        trigger_frame_index=trigger_frame_index,
        reason=reason,
    )


def print_confusion_matrix(tp: int, fn: int, fp: int, tn: int) -> None:
    print()
    print("Confusion Matrix")
    print()
    print("                         Calculated")
    print("                    FLASH        ANOMALY")
    print(f"Actual FLASH        {tp:10d}   {fn:7d}")
    print(f"Actual ANOMALY      {fp:10d}   {tn:7d}")
    print()
    print(f"TP {tp}   FN {fn}   FP {fp}   TN {tn}")

    recall_denominator = tp + fn
    precision_denominator = tp + fp
    accuracy_denominator = tp + fn + fp + tn

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
    verbosity: int,
) -> int:
    if not folder.is_dir():
        raise RuntimeError(f"Smoke-test folder not found: {folder}")

    manifest = read_manifest(manifest_path)

    expected_flash = sum(
        expected == EXPECTED_FLASH
        for expected in manifest.values()
    )
    expected_anomaly = sum(
        expected == EXPECTED_ANOMALY
        for expected in manifest.values()
    )

    results: list[TestResult] = []

    print("Running smoke tests...")

    for filename, expected in manifest.items():
        video_path = folder / filename

        print(". ", end="", flush=True)

        if not video_path.is_file():
            raise RuntimeError(f"Smoke-test MP4 not found: {video_path}")

        results.append(run_one_test(video_path, expected))

    print()

    tp = sum(
        result.expected == EXPECTED_FLASH
        and result.calculated == EXPECTED_FLASH
        for result in results
    )
    fn = sum(
        result.expected == EXPECTED_FLASH
        and result.calculated == EXPECTED_ANOMALY
        for result in results
    )
    fp = sum(
        result.expected == EXPECTED_ANOMALY
        and result.calculated == EXPECTED_FLASH
        for result in results
    )
    tn = sum(
        result.expected == EXPECTED_ANOMALY
        and result.calculated == EXPECTED_ANOMALY
        for result in results
    )

    if tp + fn != expected_flash:
        raise RuntimeError("Internal error: FLASH row does not match manifest")
    if fp + tn != expected_anomaly:
        raise RuntimeError("Internal error: ANOMALY row does not match manifest")

    incorrect = sum(not result.correct for result in results)

    print("Production Classifier Smoke Test")
    print(f"Folder:       {folder}")
    print(f"Manifest:     {manifest_path}")
    print("Input path:   saved sidecar metrics + recorded Pi trigger")
    print(
        f"Ground truth: {expected_flash} FLASH, "
        f"{expected_anomaly} ANOMALY"
    )
    print()

    filename_width = max(
        len("File"),
        *(len(result.filename) for result in results),
    )

    print(
        f"{'File':<{filename_width}}  "
        f"{'Expected':<11}  "
        f"{'Calculated':<11}  "
        f"{'Confidence':>10}  "
        f"Result"
    )
    print(
        f"{'-' * filename_width}  "
        f"{'-' * 11}  "
        f"{'-' * 11}  "
        f"{'-' * 10}  "
        f"{'-' * 9}"
    )

    for result in results:
        result_text = "CORRECT" if result.correct else "INCORRECT"
        print(
            f"{result.filename:<{filename_width}}  "
            f"{result.expected:<11}  "
            f"{result.calculated:<11}  "
            f"{result.confidence:>10.4f}  "
            f"{result_text}"
        )

    print()
    print(
        f"Tests: {len(results)}   "
        f"Correct: {len(results) - incorrect}   "
        f"Incorrect: {incorrect}"
    )

    incorrect_results = [
        result for result in results if not result.correct
    ]

    print()
    print("Incorrect Results")
    print("-----------------")

    if not incorrect_results:
        print("None.")
    else:
        for result in incorrect_results:
            print(result.filename)
            print(f"    Expected:   {result.expected}")
            print(f"    Calculated: {result.calculated}")
            print(f"    Confidence: {result.confidence:.6f}")
            print(
                f"    Pi trigger:  frame {result.trigger_frame_index + 1} "
                f"(index {result.trigger_frame_index})"
            )
            print(f"    Reason:     {result.reason}")
            print()

    if verbosity >= 1:
        print()
        print("All Result Details")
        print("------------------")

        for result in results:
            print(result.filename)
            print(f"    Expected:   {result.expected}")
            print(f"    Calculated: {result.calculated}")
            print(f"    Confidence: {result.confidence:.6f}")
            print(
                f"    Pi trigger:  frame {result.trigger_frame_index + 1} "
                f"(index {result.trigger_frame_index})"
            )
            print(f"    Reason:     {result.reason}")
            print()

    print_confusion_matrix(tp, fn, fp, tn)

    return 0 if incorrect == 0 else 1


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run the frozen production classifier against saved smoke-test "
            "sidecar metrics and recorded Pi trigger frames."
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
        "-v",
        "--verbosity",
        action="count",
        default=0,
        help="Show classifier confidence/reason for every file.",
    )

    arguments = parser.parse_args()

    folder = (
        arguments.folder
        if arguments.folder is not None
        else APPLICATION_ROOT / "testData" / "smokeTest"
    )

    manifest_path = (
        arguments.manifest
        if arguments.manifest is not None
        else folder / "solution_filter_smoke_tests.json"
    )

    try:
        return run_tests(
            folder,
            manifest_path,
            arguments.verbosity,
        )
    except (
        OSError,
        json.JSONDecodeError,
        RuntimeError,
        ValueError,
    ) as error:
        print(f"Smoke test failed: {error}")
        return 2


if __name__ == "__main__":
    exit_code = main()

    # Keep the console window open when run by double-clicking on Windows.
    print()
    if sys.platform == "win32":
        import msvcrt

        print("Press any key to exit...", end="", flush=True)
        msvcrt.getwch()
    else:
        try:
            input("Press Enter to exit...")
        except EOFError:
            pass

    sys.exit(exit_code)
