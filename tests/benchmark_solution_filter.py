#!/usr/bin/env python3
"""
Benchmark legacy vs empirical SolutionFilter classification speed.

This harness deliberately excludes JSON file I/O from the timed region:
all sidecars are loaded and converted to NumPy arrays before timing starts.

It prints timing only -- no classification results.

Usage:
    python benchmark_solution_filter.py TEST_FOLDER

Optional:
    --passes N     Number of timed passes per classifier (default: 10)
    --warmup N     Number of untimed warmup passes (default: 2)
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
from pathlib import Path
import statistics
import sys
import time

from common.candidate_config import CANDIDATE_CONFIG
from common.solution_batch import (
    build_metric_arrays,
    classify_solution_arrays,
    get_trigger_frame_index,
)
from video_analyzer.solution_config import solution_config_for_sensitivity
from video_analyzer.solution_filter import SolutionFilter


def load_cases(folder: Path) -> list[tuple]:
    cases = []

    for path in sorted(folder.rglob("*.json")):
        if not path.is_file():
            continue

        with path.open("r", encoding="utf-8-sig") as file:
            sidecar = json.load(file)

        brightness, brightness_delta = build_metric_arrays(sidecar)

        trigger_frame_index = get_trigger_frame_index(sidecar)

        if trigger_frame_index is None:
            raise RuntimeError(
                f"{path}: no valid Candidate trigger frame"
            )

        candidate = sidecar.get("candidate")

        if isinstance(candidate, dict):
            trigger_reason = str(
                candidate.get("trigger_reason", "") or ""
            )
        else:
            trigger_reason = str(
                sidecar.get("trigger_reason", "") or ""
            )

        cases.append(
            (
                brightness,
                brightness_delta,
                trigger_frame_index,
                trigger_reason,
            )
        )

    return cases


def run_legacy(
    solution_filter: SolutionFilter,
    cases: list[tuple],
) -> None:
    for (
        brightness,
        brightness_delta,
        trigger_frame_index,
        trigger_reason,
    ) in cases:
        solution_filter.evaluate(
            brightness,
            brightness_delta,
            trigger_frame_index,
            trigger_reason,
        )


def run_empirical(
    solution_filter: SolutionFilter,
    cases: list[tuple],
) -> None:
    for (
        brightness,
        brightness_delta,
        trigger_frame_index,
        trigger_reason,
    ) in cases:
        classify_solution_arrays(
            solution_filter,
            brightness,
            brightness_delta,
            trigger_frame_index,
            trigger_reason,
        )


def benchmark(
    function,
    solution_filter: SolutionFilter,
    cases: list[tuple],
    passes: int,
    warmup: int,
) -> list[float]:
    # Suppress anything a filter might write so console I/O cannot affect timing.
    sink = io.StringIO()

    with contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
        for _ in range(warmup):
            function(
                solution_filter,
                cases,
            )

        timings = []

        for _ in range(passes):
            start = time.perf_counter()

            function(
                solution_filter,
                cases,
            )

            elapsed = (
                time.perf_counter() -
                start
            )

            timings.append(elapsed)

    return timings


def print_timing(
    name: str,
    timings: list[float],
    capture_count: int,
) -> None:
    mean_seconds = statistics.mean(timings)
    median_seconds = statistics.median(timings)
    min_seconds = min(timings)
    max_seconds = max(timings)

    mean_per_capture_ms = (
        mean_seconds /
        capture_count *
        1000.0
    )

    captures_per_second = (
        capture_count /
        mean_seconds
    )

    print(name)
    print("-" * len(name))
    print(
        f"Mean total:        {mean_seconds:.6f} sec"
    )
    print(
        f"Median total:      {median_seconds:.6f} sec"
    )
    print(
        f"Fastest pass:      {min_seconds:.6f} sec"
    )
    print(
        f"Slowest pass:      {max_seconds:.6f} sec"
    )
    print(
        f"Mean per capture:  {mean_per_capture_ms:.6f} ms"
    )
    print(
        f"Throughput:        {captures_per_second:.1f} captures/sec"
    )
    print()


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Benchmark legacy and empirical SolutionFilter speed "
            "without timing JSON file I/O."
        )
    )

    parser.add_argument(
        "test_folder",
        type=Path,
        help="Folder containing JSON sidecars; scanned recursively",
    )

    parser.add_argument(
        "--passes",
        type=int,
        default=10,
        help="Timed passes per classifier (default: 10)",
    )

    parser.add_argument(
        "--warmup",
        type=int,
        default=2,
        help="Untimed warmup passes per classifier (default: 2)",
    )

    args = parser.parse_args()

    if args.passes < 1:
        print("--passes must be at least 1", file=sys.stderr)
        return 1

    if args.warmup < 0:
        print("--warmup must be >= 0", file=sys.stderr)
        return 1

    folder = args.test_folder.expanduser().resolve()

    if not folder.is_dir():
        print(
            f"Folder not found: {folder}",
            file=sys.stderr,
        )
        return 1

    try:
        cases = load_cases(folder)
    except (
        OSError,
        json.JSONDecodeError,
        RuntimeError,
        TypeError,
        ValueError,
        KeyError,
    ) as error:
        print(
            f"Unable to prepare benchmark: {error}",
            file=sys.stderr,
        )
        return 1

    if not cases:
        print(
            "No JSON sidecars found.",
            file=sys.stderr,
        )
        return 1

    solution_filter = SolutionFilter(
        solution_config_for_sensitivity(
            CANDIDATE_CONFIG.sensitivity
        )
    )

    legacy_times = benchmark(
        run_legacy,
        solution_filter,
        cases,
        args.passes,
        args.warmup,
    )

    empirical_times = benchmark(
        run_empirical,
        solution_filter,
        cases,
        args.passes,
        args.warmup,
    )

    print()
    print("SolutionFilter performance benchmark")
    print("====================================")
    print(
        f"Captures per pass:  {len(cases)}"
    )
    print(
        f"Timed passes:       {args.passes}"
    )
    print(
        f"Warmup passes:      {args.warmup}"
    )
    print()

    print_timing(
        "Legacy filter",
        legacy_times,
        len(cases),
    )

    print_timing(
        "Empirical filter",
        empirical_times,
        len(cases),
    )

    legacy_mean = statistics.mean(
        legacy_times
    )

    empirical_mean = statistics.mean(
        empirical_times
    )

    ratio = (
        empirical_mean /
        legacy_mean
        if legacy_mean > 0.0
        else float("inf")
    )

    delta_ms = (
        (
            empirical_mean -
            legacy_mean
        ) /
        len(cases) *
        1000.0
    )

    print("Comparison")
    print("----------")
    print(
        f"Empirical / legacy: {ratio:.3f}x"
    )
    print(
        f"Per-capture delta:  {delta_ms:+.6f} ms"
    )
    print()

    return 0


if __name__ == "__main__":
    sys.exit(main())
