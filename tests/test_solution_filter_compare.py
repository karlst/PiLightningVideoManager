#!/usr/bin/env python3
"""
Evaluate the frozen SolutionFilter binary classifier on an untouched JSON test set.

Usage:
    python test_solution_filter.py TEST_FOLDER

The test folder may contain JSON files in nested subfolders. Ground truth is:

    capture.classification == "TF" -> TRUE_FLASH
    anything else                 -> ANOMALY

The classifier is imported from common.solution_batch, so first replace your
project's common/solution_batch.py with the frozen rewritten version.
"""

from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import sys

from common.candidate_config import CANDIDATE_CONFIG
from common.solution_batch import (
    build_metric_arrays,
    get_trigger_frame_index,
)

try:
    from common.solution_batch import classify_solution_arrays
except ImportError:
    classify_solution_arrays = None
from video_analyzer.solution_config import solution_config_for_sensitivity
from video_analyzer.solution_filter import SolutionFilter
from video_analyzer.solution_types import CATEGORY_TRUE_FLASH


def load_sidecar(path: Path) -> dict:
    with path.open("r", encoding="utf-8-sig") as file:
        sidecar = json.load(file)

    if not isinstance(sidecar, dict):
        raise RuntimeError("Sidecar root is not a JSON object")

    capture = sidecar.get("capture")
    if not isinstance(capture, dict):
        raise RuntimeError("Sidecar is missing capture metadata")

    return sidecar


def ground_truth_binary(sidecar: dict) -> tuple[str, str]:
    classification = str(
        sidecar["capture"].get("classification", "") or ""
    ).strip().upper()

    if not classification:
        raise RuntimeError("Capture classification is missing")

    return (
        "TRUE_FLASH" if classification == "TF" else "ANOMALY",
        classification,
    )


def trigger_reason_from_sidecar(sidecar: dict) -> str:
    candidate = sidecar.get("candidate")
    if isinstance(candidate, dict):
        return str(candidate.get("trigger_reason", "") or "")

    return str(sidecar.get("trigger_reason", "") or "")


def classify_one(
    sidecar: dict,
    solution_filter: SolutionFilter,
    mode: str,
) -> tuple[str, str, str]:
    brightness, brightness_delta = build_metric_arrays(sidecar)

    trigger_frame_index = get_trigger_frame_index(sidecar)

    if trigger_frame_index is None:
        raise RuntimeError(
            "Sidecar contains no valid Candidate trigger frame"
        )

    if not 0 <= trigger_frame_index < len(brightness):
        raise RuntimeError(
            "Candidate trigger frame is outside frame_records"
        )

    trigger_reason = trigger_reason_from_sidecar(sidecar)

    if mode == "legacy":
        result = solution_filter.evaluate(
            brightness,
            brightness_delta,
            trigger_frame_index,
            trigger_reason,
        )

        category = result.category
        reason = result.reason

    elif mode == "empirical":
        if classify_solution_arrays is None:
            raise RuntimeError(
                "Empirical classifier is not available in "
                "common.solution_batch.py"
            )

        category, reason = classify_solution_arrays(
            solution_filter,
            brightness,
            brightness_delta,
            trigger_frame_index,
            trigger_reason,
        )

    else:
        raise RuntimeError(
            f"Unknown classifier mode: {mode}"
        )

    binary = (
        "TRUE_FLASH"
        if category == CATEGORY_TRUE_FLASH
        else "ANOMALY"
    )

    return binary, category, reason


def pct(numerator: int, denominator: int) -> float:
    return 0.0 if denominator == 0 else 100.0 * numerator / denominator


def evaluate_mode(
    json_files: list[Path],
    mode: str,
) -> dict:
    solution_filter = SolutionFilter(
        solution_config_for_sensitivity(
            CANDIDATE_CONFIG.sensitivity
        )
    )

    tp = fn = fp = tn = 0
    skipped = []
    false_negatives = []
    false_positives = []
    truth_counts = Counter()
    predicted_category_counts = Counter()
    subtype_results = Counter()

    for path in json_files:
        try:
            sidecar = load_sidecar(path)
            truth_binary, truth_classification = ground_truth_binary(sidecar)
            predicted_binary, predicted_category, reason = classify_one(
                sidecar,
                solution_filter,
                mode,
            )
        except (
            OSError,
            json.JSONDecodeError,
            RuntimeError,
            TypeError,
            ValueError,
            KeyError,
        ) as error:
            skipped.append((path, str(error)))
            continue

        truth_counts[truth_classification] += 1
        predicted_category_counts[predicted_category] += 1
        subtype_results[(truth_classification, predicted_binary)] += 1

        if truth_binary == "TRUE_FLASH":
            if predicted_binary == "TRUE_FLASH":
                tp += 1
            else:
                fn += 1
                false_negatives.append(
                    (path, predicted_category, reason)
                )
        else:
            if predicted_binary == "TRUE_FLASH":
                fp += 1
                false_positives.append(
                    (
                        path,
                        truth_classification,
                        predicted_category,
                        reason,
                    )
                )
            else:
                tn += 1

    return {
        "mode": mode,
        "tp": tp,
        "fn": fn,
        "fp": fp,
        "tn": tn,
        "skipped": skipped,
        "false_negatives": false_negatives,
        "false_positives": false_positives,
        "truth_counts": truth_counts,
        "predicted_category_counts": predicted_category_counts,
        "subtype_results": subtype_results,
    }


def print_result(result: dict) -> None:
    mode = result["mode"]
    tp = result["tp"]
    fn = result["fn"]
    fp = result["fp"]
    tn = result["tn"]
    skipped = result["skipped"]
    false_negatives = result["false_negatives"]
    false_positives = result["false_positives"]
    truth_counts = result["truth_counts"]
    predicted_category_counts = result["predicted_category_counts"]
    subtype_results = result["subtype_results"]

    evaluated = tp + fn + fp + tn
    actual_tf = tp + fn
    actual_anomaly = fp + tn
    predicted_tf = tp + fp

    print()
    print(f"{mode.upper()} classifier")
    print("=" * (len(mode) + 11))
    print()
    print("Binary confusion matrix")
    print("-----------------------")
    print("                         Predicted")
    print("                    TRUE_FLASH    ANOMALY")
    print(f"Actual TRUE_FLASH   {tp:>10} {fn:>10}")
    print(f"Actual ANOMALY      {fp:>10} {tn:>10}")
    print()
    print(f"Evaluated:                 {evaluated}")
    print(f"Skipped:                   {len(skipped)}")
    print(f"TF recall:                 {pct(tp, actual_tf):.2f}%")
    print(f"TF precision:              {pct(tp, predicted_tf):.2f}%")
    print(f"Anomaly rejection rate:    {pct(tn, actual_anomaly):.2f}%")
    print(f"False-positive rate:       {pct(fp, actual_anomaly):.2f}%")
    print(f"Overall accuracy:          {pct(tp + tn, evaluated):.2f}%")

    print()
    print("Ground-truth classification breakdown")
    print("-------------------------------------")
    for classification, count in sorted(truth_counts.items()):
        pred_tf = subtype_results[(classification, "TRUE_FLASH")]
        pred_anom = subtype_results[(classification, "ANOMALY")]
        print(
            f"{classification:<8} "
            f"total={count:>5}  "
            f"pred TF={pred_tf:>5}  "
            f"pred anomaly={pred_anom:>5}"
        )

    if false_negatives:
        print()
        print("FALSE NEGATIVES -- real flashes rejected")
        for path, predicted_category, reason in false_negatives:
            print(path)
            print(f"    predicted category: {predicted_category}")
            print(f"    {reason}")

    if false_positives:
        print()
        print("FALSE POSITIVES -- anomalies passed as flashes")
        for (
            path,
            truth_classification,
            predicted_category,
            reason,
        ) in false_positives:
            print(path)
            print(f"    actual classification: {truth_classification}")
            print(f"    predicted category: {predicted_category}")
            print(f"    {reason}")


def print_comparison(
    legacy: dict,
    empirical: dict,
) -> None:
    def metrics(r):
        tp, fn, fp, tn = r["tp"], r["fn"], r["fp"], r["tn"]
        return {
            "tp": tp,
            "fn": fn,
            "fp": fp,
            "tn": tn,
            "recall": pct(tp, tp + fn),
            "precision": pct(tp, tp + fp),
            "rejection": pct(tn, tn + fp),
            "accuracy": pct(tp + tn, tp + fn + fp + tn),
        }

    a = metrics(legacy)
    b = metrics(empirical)

    print()
    print("SIDE-BY-SIDE COMPARISON")
    print("=======================")
    print(f"{'Metric':<28}{'Legacy':>12}{'Empirical':>12}")
    print(f"{'True positives':<28}{a['tp']:>12}{b['tp']:>12}")
    print(f"{'False negatives':<28}{a['fn']:>12}{b['fn']:>12}")
    print(f"{'False positives':<28}{a['fp']:>12}{b['fp']:>12}")
    print(f"{'True negatives':<28}{a['tn']:>12}{b['tn']:>12}")
    print(f"{'TF recall':<28}{a['recall']:>11.2f}%{b['recall']:>11.2f}%")
    print(f"{'TF precision':<28}{a['precision']:>11.2f}%{b['precision']:>11.2f}%")
    print(f"{'Anomaly rejection':<28}{a['rejection']:>11.2f}%{b['rejection']:>11.2f}%")
    print(f"{'Overall accuracy':<28}{a['accuracy']:>11.2f}%{b['accuracy']:>11.2f}%")


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Evaluate legacy and/or empirical SolutionFilter logic "
            "against an untouched JSON test set."
        )
    )
    parser.add_argument(
        "test_folder",
        type=Path,
        help="Folder containing test JSON sidecars; scanned recursively",
    )
    parser.add_argument(
        "--classifier",
        choices=("legacy", "empirical", "both"),
        default="both",
        help=(
            "Classifier to evaluate. Default 'both' runs the existing "
            "rule-based SolutionFilter and the new empirical classifier."
        ),
    )
    args = parser.parse_args()

    test_folder = args.test_folder.expanduser().resolve()

    if not test_folder.is_dir():
        print(f"Test folder not found: {test_folder}", file=sys.stderr)
        return 1

    json_files = sorted(
        path for path in test_folder.rglob("*.json") if path.is_file()
    )

    if not json_files:
        print(f"No JSON files found under: {test_folder}", file=sys.stderr)
        return 1

    print(f"Test JSON files found: {len(json_files)}")

    modes = (
        ("legacy", "empirical")
        if args.classifier == "both"
        else (args.classifier,)
    )

    results = {}

    for mode in modes:
        if mode == "empirical" and classify_solution_arrays is None:
            print(
                "Empirical classifier is not present in "
                "common/solution_batch.py",
                file=sys.stderr,
            )
            return 1

        result = evaluate_mode(json_files, mode)
        results[mode] = result
        print_result(result)

    if args.classifier == "both":
        print_comparison(
            results["legacy"],
            results["empirical"],
        )

    skipped_count = sum(
        len(result["skipped"])
        for result in results.values()
    )

    print()
    return 0 if skipped_count == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
