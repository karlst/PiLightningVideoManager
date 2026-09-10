"""
Train a replacement logistic-regression model for Pi Camera Capture.

The script reuses common.classification_model.build_classification_features so
training and production use exactly the same 20 feature definitions and order.

It trains a class-balanced logistic regression where predict_proba[:, 1] is P(FLASH),\nreports stratified 5-fold
cross-validation and final in-sample metrics, and writes a complete model module
using the compact format:

    MODEL_FEATURES = {
        "feature": (mean, scale, coefficient),
        ...
    }

The generated model is NOT activated automatically. Validate it first, then
change the import in common/classification_model.py deliberately.

Requires scikit-learn for training only. Production does not require sklearn.

Example:
    python train_classifier.py E:\SideCarsFromS3\training ^
        --model-name logistic-v2 ^
        --output common\models\logistic_v2.py
"""

from __future__ import annotations

import argparse
import json
import math
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import confusion_matrix
from sklearn.model_selection import StratifiedKFold, cross_val_predict
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from common.classification_model import FEATURE_NAMES, build_classification_features


FLASH_LABELS = {"FLASH", "TF", "TRUE_FLASH"}
ANOMALY_LABELS = {"ANOMALY", "NA", "NAC", "SSA", "STA", "FDA", "UFA"}


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8-sig") as file:
        sidecar = json.load(file)
    if not isinstance(sidecar, dict):
        raise RuntimeError("Sidecar root must be an object")
    return sidecar


def classification_from_sidecar(sidecar: dict[str, Any]) -> str:
    capture = sidecar.get("capture")
    if not isinstance(capture, dict):
        raise RuntimeError("Missing capture object")
    value = str(capture.get("classification", "") or "").strip().upper()
    if not value:
        raise RuntimeError("Missing capture.classification")
    return value


def binary_label(classification: str) -> int:
    if classification in FLASH_LABELS:
        return 1
    if classification in ANOMALY_LABELS:
        return 0
    raise RuntimeError(f"Unsupported classification: {classification}")


def classifier_inputs(sidecar: dict[str, Any]) -> tuple[np.ndarray, np.ndarray, int]:
    records = sidecar.get("frame_records")
    if not isinstance(records, list) or not records:
        raise RuntimeError("Missing frame_records")

    brightness = np.asarray(
        [float(record["mean_brightness"]) for record in records],
        dtype=np.float64,
    )
    delta = np.asarray(
        [float(record["brightness_delta_adjacent"]) for record in records],
        dtype=np.float64,
    )

    candidate = sidecar.get("candidate")
    trigger = None
    if isinstance(candidate, dict):
        trigger = candidate.get("trigger_frame_index")
        if trigger is None:
            frame_number = candidate.get("trigger_frame_number")
            if frame_number is not None:
                trigger = int(frame_number) - 1

    if trigger is None:
        raise RuntimeError("Missing recorded trigger frame")

    return brightness, delta, int(trigger)


def load_training_set(folder: Path):
    x_rows = []
    labels = []
    original_labels = []
    paths = []

    for path in sorted(folder.rglob("*.json")):
        try:
            sidecar = read_json(path)
            original = classification_from_sidecar(sidecar)
            label = binary_label(original)
            brightness, delta, trigger = classifier_inputs(sidecar)
            features = build_classification_features(brightness, delta, trigger)
        except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError, RuntimeError) as error:
            print(f"SKIP {path}: {error}")
            continue

        x_rows.append(features)
        labels.append(label)
        original_labels.append(original)
        paths.append(path)

    if not x_rows:
        raise RuntimeError("No usable training sidecars found")

    x = np.vstack(x_rows).astype(np.float64, copy=False)
    y = np.asarray(labels, dtype=np.int64)

    if x.shape[1] != len(FEATURE_NAMES):
        raise RuntimeError(
            f"Expected {len(FEATURE_NAMES)} features; got {x.shape[1]}"
        )
    if len(np.unique(y)) != 2:
        raise RuntimeError("Training set must contain FLASH and ANOMALY")

    return x, y, paths, original_labels


def print_metrics(title: str, y, probabilities, threshold: float) -> None:
    predicted = (probabilities >= threshold).astype(np.int64)
    tn, fp, fn, tp = confusion_matrix(y, predicted, labels=[0, 1]).ravel()

    recall = tp / (tp + fn) if tp + fn else math.nan
    precision = tp / (tp + fp) if tp + fp else math.nan
    anomaly_rejection = tn / (tn + fp) if tn + fp else math.nan
    accuracy = (tp + tn) / len(y)

    print()
    print(title)
    print("-" * len(title))
    print(f"TP:                {tp}")
    print(f"FN:                {fn}")
    print(f"FP:                {fp}")
    print(f"TN:                {tn}")
    print(f"FLASH recall:      {recall:.2%}")
    print(f"FLASH precision:   {precision:.2%}")
    print(f"Anomaly rejection: {anomaly_rejection:.2%}")
    print(f"Overall accuracy:  {accuracy:.2%}")


def print_subtype_false_positives(y, probabilities, original_labels, threshold) -> None:
    predicted = (probabilities >= threshold).astype(np.int64)
    totals = Counter()
    false_positives = Counter()

    for actual, pred, subtype in zip(y, predicted, original_labels):
        if actual == 0:
            totals[subtype] += 1
            if pred == 1:
                false_positives[subtype] += 1

    print()
    print("Anomaly subtype false positives")
    print("-------------------------------")
    print(f"{'Subtype':<10} {'FP':>5} {'Total':>7} {'FP rate':>9}")
    for subtype in sorted(totals):
        total = totals[subtype]
        fp = false_positives[subtype]
        print(f"{subtype:<10} {fp:>5} {total:>7} {fp / total:>8.2%}")


def model_module_text(model_name: str, scaler, classifier) -> str:
    means = np.asarray(scaler.mean_, dtype=np.float64)
    scales = np.asarray(scaler.scale_, dtype=np.float64)
    coefficients = np.asarray(classifier.coef_[0], dtype=np.float64)
    intercept = float(classifier.intercept_[0])

    lines = [
        '"""Frozen trained parameters generated by train_classifier.py."""',
        "",
        f'MODEL_NAME = {model_name!r}',
        f"MODEL_INTERCEPT = {intercept!r}",
        "",
        "# feature_name: (mean, scale, coefficient)",
        "MODEL_FEATURES = {",
    ]

    for name, mean, scale, coefficient in zip(
        FEATURE_NAMES, means, scales, coefficients
    ):
        lines.append(
            f'    {name!r}: ({float(mean)!r}, {float(scale)!r}, '
            f'{float(coefficient)!r}),'
        )

    lines.extend(["}", ""])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("training_folder", type=Path)
    parser.add_argument("--model-name", default="logistic-v2")
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--threshold", type=float, default=0.30)
    parser.add_argument("--folds", type=int, default=5)
    parser.add_argument("--seed", type=int, default=3709)
    args = parser.parse_args()

    if not args.training_folder.is_dir():
        raise RuntimeError(f"Training folder not found: {args.training_folder}")
    if not 0.0 < args.threshold < 1.0:
        raise RuntimeError("--threshold must be between 0 and 1")
    if args.folds < 2:
        raise RuntimeError("--folds must be at least 2")

    x, y, _paths, original_labels = load_training_set(args.training_folder)

    print(f"Training sidecars: {len(y)}")
    print(f"FLASH:             {int(np.sum(y == 1))}")
    print(f"ANOMALY:           {int(np.sum(y == 0))}")
    print(f"Features:          {x.shape[1]}")

    pipeline = Pipeline(
        [
            ("scaler", StandardScaler()),
            (
                "classifier",
                LogisticRegression(
                    class_weight="balanced",
                    max_iter=10000,
                    solver="lbfgs",
                    random_state=args.seed,
                ),
            ),
        ]
    )

    cv = StratifiedKFold(
        n_splits=args.folds,
        shuffle=True,
        random_state=args.seed,
    )
    cv_probabilities = cross_val_predict(
        pipeline,
        x,
        y,
        cv=cv,
        method="predict_proba",
    )[:, 1]

    print_metrics(
        "Stratified cross-validation",
        y,
        cv_probabilities,
        args.threshold,
    )
    print_subtype_false_positives(
        y,
        cv_probabilities,
        original_labels,
        args.threshold,
    )

    pipeline.fit(x, y)
    scaler = pipeline.named_steps["scaler"]
    classifier = pipeline.named_steps["classifier"]

    train_probabilities = pipeline.predict_proba(x)[:, 1]
    print_metrics(
        "Final fit on complete training set (optimistic / in-sample)",
        y,
        train_probabilities,
        args.threshold,
    )
    print_subtype_false_positives(
        y,
        train_probabilities,
        original_labels,
        args.threshold,
    )

    text = model_module_text(args.model_name, scaler, classifier)

    if args.output is None:
        print()
        print(text)
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
        print()
        print(f"Wrote model: {args.output}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
