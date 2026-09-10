#!/usr/bin/env python3
"""
Split verified capture JSON sidecars into training and test sets.

The source folder may contain JSON files in nested subfolders. The script scans
recursively, reads each sidecar, and stratifies by:

    capture.classification
    capture.type

For each (classification, type) group, 25% of files are placed in the test set
and the remaining 75% in the training set.

Usage:
    python split_verified_sidecars.py SOURCE_FOLDER

The script creates:
    SOURCE_FOLDER/training/
    SOURCE_FOLDER/test/

Files are copied, not moved. Existing training/ and test/ folders are ignored
during the source scan.

A deterministic random seed is used by default so the same input set produces
the same split.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import random
import shutil
import sys


DEFAULT_TEST_FRACTION = 0.25
DEFAULT_SEED = 3709


def read_classification_and_type(
    path: Path,
) -> tuple[str, str]:
    with path.open(
        "r",
        encoding="utf-8-sig",
    ) as file:
        sidecar = json.load(file)

    if not isinstance(sidecar, dict):
        raise RuntimeError(
            "Sidecar root is not a JSON object"
        )

    capture = sidecar.get("capture")

    if not isinstance(capture, dict):
        raise RuntimeError(
            "Sidecar is missing capture metadata"
        )

    classification = str(
        capture.get(
            "classification",
            "",
        ) or ""
    ).strip().upper()

    capture_type = str(
        capture.get(
            "type",
            "UK",
        ) or "UK"
    ).strip().upper()

    if not classification:
        raise RuntimeError(
            "Capture classification is missing"
        )

    if not capture_type:
        capture_type = "UK"

    return classification, capture_type


def source_json_files(
    source_folder: Path,
    training_folder: Path,
    test_folder: Path,
) -> list[Path]:
    files: list[Path] = []

    for path in source_folder.rglob("*.json"):
        try:
            path.relative_to(training_folder)
            continue
        except ValueError:
            pass

        try:
            path.relative_to(test_folder)
            continue
        except ValueError:
            pass

        if path.is_file():
            files.append(path)

    return sorted(files)


def unique_destination(
    destination_folder: Path,
    source_path: Path,
    source_root: Path,
) -> Path:
    """
    Preserve relative source structure where possible.

    Example:
        source/TF/CG/foo.json
        -> training/TF/CG/foo.json
    """
    relative = source_path.relative_to(source_root)
    destination = destination_folder / relative
    destination.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    return destination


def choose_test_count(
    group_size: int,
    test_fraction: float,
) -> int:
    if group_size <= 0:
        return 0

    # Round to nearest integer while ensuring any group with at least 2 files
    # contributes to both training and test.
    count = int(
        round(
            group_size * test_fraction
        )
    )

    if group_size >= 2:
        count = max(
            1,
            min(
                group_size - 1,
                count,
            ),
        )
    else:
        count = 0

    return count


def split_sidecars(
    source_folder: Path,
    test_fraction: float,
    seed: int,
) -> int:
    source_folder = source_folder.expanduser().resolve()

    if not source_folder.is_dir():
        raise RuntimeError(
            f"Source folder not found: {source_folder}"
        )

    training_folder = source_folder / "training"
    test_folder = source_folder / "test"

    training_folder.mkdir(
        parents=True,
        exist_ok=True,
    )
    test_folder.mkdir(
        parents=True,
        exist_ok=True,
    )

    files = source_json_files(
        source_folder,
        training_folder,
        test_folder,
    )

    if not files:
        raise RuntimeError(
            "No JSON files found"
        )

    groups: dict[
        tuple[str, str],
        list[Path],
    ] = defaultdict(list)

    skipped: list[
        tuple[Path, str]
    ] = []

    for path in files:
        try:
            classification, capture_type = (
                read_classification_and_type(
                    path
                )
            )

            groups[
                (
                    classification,
                    capture_type,
                )
            ].append(
                path
            )

        except (
            OSError,
            json.JSONDecodeError,
            RuntimeError,
        ) as error:
            skipped.append(
                (
                    path,
                    str(error),
                )
            )

    rng = random.Random(seed)

    training_files: list[
        tuple[Path, str, str]
    ] = []

    test_files: list[
        tuple[Path, str, str]
    ] = []

    group_summary: list[
        tuple[str, str, int, int, int]
    ] = []

    for (
        classification,
        capture_type,
    ), group_files in sorted(
        groups.items()
    ):
        group_files = list(group_files)
        rng.shuffle(group_files)

        test_count = choose_test_count(
            len(group_files),
            test_fraction,
        )

        group_test = group_files[
            :test_count
        ]

        group_training = group_files[
            test_count:
        ]

        training_files.extend(
            (
                path,
                classification,
                capture_type,
            )
            for path in group_training
        )

        test_files.extend(
            (
                path,
                classification,
                capture_type,
            )
            for path in group_test
        )

        group_summary.append(
            (
                classification,
                capture_type,
                len(group_files),
                len(group_training),
                len(group_test),
            )
        )

    # Clear only files from previous runs inside training/test.
    for destination_root in (
        training_folder,
        test_folder,
    ):
        for old_file in destination_root.rglob("*.json"):
            old_file.unlink()

        # Remove empty directories from deepest first.
        for directory in sorted(
            (
                p
                for p in destination_root.rglob("*")
                if p.is_dir()
            ),
            key=lambda p: len(p.parts),
            reverse=True,
        ):
            try:
                directory.rmdir()
            except OSError:
                pass

    for (
        path,
        _classification,
        _capture_type,
    ) in training_files:
        destination = unique_destination(
            training_folder,
            path,
            source_folder,
        )

        shutil.copy2(
            path,
            destination,
        )

    for (
        path,
        _classification,
        _capture_type,
    ) in test_files:
        destination = unique_destination(
            test_folder,
            path,
            source_folder,
        )

        shutil.copy2(
            path,
            destination,
        )

    training_class_counts = Counter(
        classification
        for (
            _path,
            classification,
            _capture_type,
        ) in training_files
    )

    test_class_counts = Counter(
        classification
        for (
            _path,
            classification,
            _capture_type,
        ) in test_files
    )

    training_type_counts = Counter(
        capture_type
        for (
            _path,
            _classification,
            capture_type,
        ) in training_files
    )

    test_type_counts = Counter(
        capture_type
        for (
            _path,
            _classification,
            capture_type,
        ) in test_files
    )

    print()
    print("Split summary")
    print("=============")
    print(
        f"Source JSON files: {len(files)}"
    )
    print(
        f"Usable JSON files: "
        f"{len(training_files) + len(test_files)}"
    )
    print(
        f"Training files: {len(training_files)}"
    )
    print(
        f"Test files: {len(test_files)}"
    )
    print(
        f"Skipped files: {len(skipped)}"
    )
    print(
        f"Requested test fraction: "
        f"{test_fraction:.1%}"
    )
    print(
        f"Random seed: {seed}"
    )
    print()

    print(
        "By classification / type:"
    )
    print(
        f"{'Classification':<16}"
        f"{'Type':<8}"
        f"{'Total':>8}"
        f"{'Train':>8}"
        f"{'Test':>8}"
        f"{'Test %':>9}"
    )

    for (
        classification,
        capture_type,
        total,
        train_count,
        test_count,
    ) in group_summary:
        pct = (
            (100.0 * test_count / total)
            if total > 0
            else 0.0
        )

        print(
            f"{classification:<16}"
            f"{capture_type:<8}"
            f"{total:>8}"
            f"{train_count:>8}"
            f"{test_count:>8}"
            f"{pct:>8.1f}%"
        )

    print()
    print("By classification:")
    all_classifications = sorted(
        set(training_class_counts)
        | set(test_class_counts)
    )

    for classification in all_classifications:
        print(
            f"  {classification:<12} "
            f"train={training_class_counts[classification]:>5}  "
            f"test={test_class_counts[classification]:>5}"
        )

    print()
    print("By type:")
    all_types = sorted(
        set(training_type_counts)
        | set(test_type_counts)
    )

    for capture_type in all_types:
        print(
            f"  {capture_type:<12} "
            f"train={training_type_counts[capture_type]:>5}  "
            f"test={test_type_counts[capture_type]:>5}"
        )

    if skipped:
        print()
        print("Skipped files:")
        for path, reason in skipped:
            print(
                f"  {path}: {reason}"
            )

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Split verified capture sidecars into stratified "
            "training and test sets."
        )
    )

    parser.add_argument(
        "source_folder",
        type=Path,
        help=(
            "Folder containing verified JSON sidecars. "
            "training/ and test/ will be created inside it."
        ),
    )

    parser.add_argument(
        "--test-fraction",
        type=float,
        default=DEFAULT_TEST_FRACTION,
        help=(
            "Fraction of each classification/type group assigned "
            f"to test (default: {DEFAULT_TEST_FRACTION})"
        ),
    )

    parser.add_argument(
        "--seed",
        type=int,
        default=DEFAULT_SEED,
        help=(
            "Deterministic random seed "
            f"(default: {DEFAULT_SEED})"
        ),
    )

    arguments = parser.parse_args()

    if not 0.0 < arguments.test_fraction < 1.0:
        print(
            "--test-fraction must be between 0 and 1",
            file=sys.stderr,
        )
        return 1

    try:
        return split_sidecars(
            arguments.source_folder,
            arguments.test_fraction,
            arguments.seed,
        )

    except (
        OSError,
        RuntimeError,
        ValueError,
    ) as error:
        print(
            f"Split failed: {error}",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
