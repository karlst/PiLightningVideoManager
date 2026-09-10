"""
Regression-test the selected classifier against the original empirical
solution_batch.py.

Usage:
    python regression_test_classifier.py OLD_SOLUTION_BATCH TRAINING_FOLDER

The reference file is parsed with AST so only the original frozen model
constants and feature/probability functions execute. Every usable sidecar is
compared for:

    20-feature vector
    standardized feature vector
    raw logistic score
    P(FLASH)
    final decision at the current configured threshold
"""

from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path

import numpy as np

from common.classification_config import CLASSIFICATION_FLASH_CONFIDENCE_THRESHOLD
from common.classification_model import classification_diagnostics


_REFERENCE_NAMES = {
    "_BINARY_FEATURE_MEANS",
    "_BINARY_FEATURE_SCALES",
    "_BINARY_FEATURE_COEFFICIENTS",
    "_BINARY_INTERCEPT",
}
_REFERENCE_FUNCTIONS = {
    "_median_absolute_deviation",
    "_finite_quantile",
    "build_binary_flash_features",
    "binary_true_flash_probability",
}


def load_reference(old_solution_batch: Path) -> dict:
    tree = ast.parse(old_solution_batch.read_text(encoding="utf-8-sig"))
    nodes = []

    for node in tree.body:
        if isinstance(node, ast.Assign):
            names = {
                target.id
                for target in node.targets
                if isinstance(target, ast.Name)
            }
            if names & _REFERENCE_NAMES:
                nodes.append(node)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if node.target.id in _REFERENCE_NAMES:
                nodes.append(node)
        elif isinstance(node, ast.FunctionDef) and node.name in _REFERENCE_FUNCTIONS:
            nodes.append(node)

    module = ast.Module(body=nodes, type_ignores=[])
    ast.fix_missing_locations(module)
    namespace = {"np": np, "RuntimeError": RuntimeError}
    exec(compile(module, str(old_solution_batch), "exec"), namespace)

    missing = (_REFERENCE_NAMES | _REFERENCE_FUNCTIONS) - namespace.keys()
    if missing:
        raise RuntimeError(f"Reference model pieces not found: {sorted(missing)}")

    return namespace


def arrays_from_sidecar(path: Path) -> tuple[np.ndarray, np.ndarray, int]:
    sidecar = json.loads(path.read_text(encoding="utf-8-sig"))
    records = sidecar["frame_records"]
    brightness = np.asarray(
        [float(record["mean_brightness"]) for record in records],
        dtype=np.float64,
    )
    delta = np.asarray(
        [float(record["brightness_delta_adjacent"]) for record in records],
        dtype=np.float64,
    )

    candidate = sidecar.get("candidate", {})
    trigger = candidate.get("trigger_frame_index") if isinstance(candidate, dict) else None
    if trigger is None and isinstance(candidate, dict):
        frame_number = candidate.get("trigger_frame_number")
        if frame_number is not None:
            trigger = int(frame_number) - 1
    if trigger is None:
        raise RuntimeError("No trigger frame")

    return brightness, delta, int(trigger)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("old_solution_batch", type=Path)
    parser.add_argument("sidecar_folder", type=Path)
    args = parser.parse_args()

    reference = load_reference(args.old_solution_batch)
    paths = sorted(args.sidecar_folder.rglob("*.json"))
    if not paths:
        raise RuntimeError("No JSON sidecars found")

    max_feature_diff = 0.0
    max_standardized_diff = 0.0
    max_logit_diff = 0.0
    max_probability_diff = 0.0
    decision_mismatches = 0
    compared = 0

    for path in paths:
        try:
            brightness, delta, trigger = arrays_from_sidecar(path)
        except (KeyError, TypeError, ValueError, RuntimeError):
            continue

        old_features = reference["build_binary_flash_features"](
            brightness, delta, trigger
        )
        old_standardized = (
            (old_features - reference["_BINARY_FEATURE_MEANS"])
            / reference["_BINARY_FEATURE_SCALES"]
        )
        old_logit = float(
            reference["_BINARY_INTERCEPT"]
            + np.dot(
                old_standardized,
                reference["_BINARY_FEATURE_COEFFICIENTS"],
            )
        )
        old_probability = reference["binary_true_flash_probability"](
            brightness, delta, trigger
        )

        new_features, new_standardized, new_logit, new_probability = (
            classification_diagnostics(brightness, delta, trigger)
        )

        max_feature_diff = max(
            max_feature_diff,
            float(np.max(np.abs(old_features - new_features))),
        )
        max_standardized_diff = max(
            max_standardized_diff,
            float(np.max(np.abs(old_standardized - new_standardized))),
        )
        max_logit_diff = max(max_logit_diff, abs(old_logit - new_logit))
        max_probability_diff = max(
            max_probability_diff,
            abs(old_probability - new_probability),
        )

        old_decision = (
            old_probability >= CLASSIFICATION_FLASH_CONFIDENCE_THRESHOLD
        )
        new_decision = (
            new_probability >= CLASSIFICATION_FLASH_CONFIDENCE_THRESHOLD
        )
        decision_mismatches += int(old_decision != new_decision)
        compared += 1

    print(f"Compared:                  {compared}")
    print(f"Max feature abs diff:      {max_feature_diff:.17g}")
    print(f"Max standardized abs diff: {max_standardized_diff:.17g}")
    print(f"Max logit abs diff:        {max_logit_diff:.17g}")
    print(f"Max P(FLASH) abs diff:   {max_probability_diff:.17g}")
    print(f"Decision mismatches:       {decision_mismatches}")

    return 0 if (
        max_feature_diff == 0.0
        and max_standardized_diff == 0.0
        and max_logit_diff == 0.0
        and max_probability_diff == 0.0
        and decision_mismatches == 0
    ) else 1


if __name__ == "__main__":
    raise SystemExit(main())
