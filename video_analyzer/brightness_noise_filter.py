"""Detect sustained brightness-delta oscillation away from the trigger event.

Brightness noise is repeated positive/negative change of meaningful magnitude
over a substantial number of frames. The Candidate event itself is excluded.

The exclusion window is asymmetric. When enough pre-trigger frames exist to
measure a trustworthy brightness baseline, post-trigger noise analysis is
deferred until brightness has returned to that baseline for a sustained run.
If the trigger occurs too early to establish a baseline, the original
post-trigger noise search is preserved unchanged.

A delta is meaningful only when its absolute magnitude reaches the effective
noise threshold:

    max(configured absolute minimum,
        largest absolute clip delta * configured max-delta fraction)

This lets the noise floor scale with event strength while retaining an absolute
minimum for clips whose largest delta is small.
"""

from __future__ import annotations

import numpy as np

from video_analyzer.solution_types import CATEGORY_BRIGHT_NOISE
from video_analyzer.solution_types import CATEGORY_TRUE_FLASH
from video_analyzer.solution_types import SolutionResult


class BrightnessNoiseFilter:
    """Reject sustained meaningful brightness oscillation."""

    def __init__(
        self,
        window_frames: int = 100,
        trigger_exclusion_before_frames: int = 10,
        trigger_exclusion_after_frames: int = 50,
        minimum_delta_magnitude: float = 0.5,
        max_delta_fraction: float = 0.02,
        minimum_meaningful_samples: int = 50,
        minimum_sign_changes: int = 40,
        baseline_frames: int = 30,
        baseline_minimum_tolerance: float = 1.0,
        baseline_mad_multiplier: float = 4.0,
        return_to_baseline_frames: int = 25,
    ) -> None:
        self._window_frames = int(window_frames)
        self._trigger_exclusion_before_frames = int(
            trigger_exclusion_before_frames
        )
        self._trigger_exclusion_after_frames = int(
            trigger_exclusion_after_frames
        )
        self._minimum_delta_magnitude = float(minimum_delta_magnitude)
        self._max_delta_fraction = float(max_delta_fraction)
        self._minimum_meaningful_samples = int(minimum_meaningful_samples)
        self._minimum_sign_changes = int(minimum_sign_changes)
        self._baseline_frames = int(baseline_frames)
        self._baseline_minimum_tolerance = float(
            baseline_minimum_tolerance
        )
        self._baseline_mad_multiplier = float(
            baseline_mad_multiplier
        )
        self._return_to_baseline_frames = int(
            return_to_baseline_frames
        )

    def evaluate(
        self,
        brightness: np.ndarray,
        brightness_delta: np.ndarray,
        trigger_frame_index: int | None,
    ) -> SolutionResult:

        finite_deltas = np.asarray(
            brightness_delta,
            dtype=np.float64,
        )
        finite_deltas = finite_deltas[
            np.isfinite(finite_deltas)
        ]

        max_abs_delta = (
            float(np.max(np.abs(finite_deltas)))
            if finite_deltas.size
            else 0.0
        )

        effective_threshold = max(
            self._minimum_delta_magnitude,
            max_abs_delta * self._max_delta_fraction,
        )

        result = self._find_noise_window(
            np.asarray(brightness, dtype=np.float64),
            brightness_delta,
            trigger_frame_index,
            effective_threshold,
        )

        if result is not None:
            start_index, end_index, meaningful_samples, sign_changes = result
            return SolutionResult(
                is_solution=False,
                category=CATEGORY_BRIGHT_NOISE,
                reason=(
                    "Brightness noise detected: "
                    f"frames {start_index + 1}-{end_index}, "
                    f"{meaningful_samples} deltas with "
                    f"|delta| >= {effective_threshold:.3f} "
                    f"(max |delta| {max_abs_delta:.3f} x "
                    f"{self._max_delta_fraction:.3f}; "
                    f"absolute floor {self._minimum_delta_magnitude:.3f}), "
                    f"{sign_changes} sign changes"
                ),
            )

        return SolutionResult(
            is_solution=True,
            category=CATEGORY_TRUE_FLASH,
            reason="Brightness noise filter passed",
        )

    def _find_noise_window(
        self,
        brightness: np.ndarray,
        brightness_delta: np.ndarray,
        trigger_frame_index: int | None,
        effective_threshold: float,
    ) -> tuple[int, int, int, int] | None:
        frame_count = min(
            len(brightness),
            len(brightness_delta),
        )

        if frame_count == 0 or trigger_frame_index is None:
            return None

        if not 0 <= trigger_frame_index < frame_count:
            return None

        exclusion_start = max(
            0,
            trigger_frame_index -
            self._trigger_exclusion_before_frames,
        )
        exclusion_end = min(
            frame_count,
            trigger_frame_index +
            self._trigger_exclusion_after_frames +
            1,
        )

        # Preserve the original pre-trigger search exactly.
        result = self._search_region(
            brightness_delta,
            0,
            exclusion_start,
            effective_threshold,
        )
        if result is not None:
            return result

        # If there is not enough pre-trigger history to establish a reliable
        # baseline, preserve the original post-trigger behavior exactly.
        #
        # This is important for clips such as nightNoise01/02/03 whose replay
        # trigger occurs at frames 2-3. Those clips must still be rejected by
        # the original brightness-noise detector.
        if exclusion_start < self._baseline_frames:
            return self._search_region(
                brightness_delta,
                exclusion_end,
                frame_count,
                effective_threshold,
            )

        baseline = self._measure_baseline(
            brightness,
            exclusion_start,
        )

        # Defensive fallback: if the baseline cannot be measured for any
        # reason, do not weaken the existing detector.
        if baseline is None:
            return self._search_region(
                brightness_delta,
                exclusion_end,
                frame_count,
                effective_threshold,
            )

        baseline_level, baseline_tolerance = baseline

        # With a trustworthy pre-trigger baseline, protect long/multi-pulse
        # lightning from being called "noise" while the flash is still active.
        post_trigger_start = self._find_return_to_baseline(
            brightness,
            exclusion_end,
            frame_count,
            baseline_level,
            baseline_tolerance,
        )

        # If the signal never returns to baseline, do not treat the still-active
        # flash itself as post-trigger background noise.
        if post_trigger_start is None:
            return None

        return self._search_region(
            brightness_delta,
            post_trigger_start,
            frame_count,
            effective_threshold,
        )

    def _measure_baseline(
        self,
        brightness: np.ndarray,
        baseline_end: int,
    ) -> tuple[float, float] | None:
        baseline_start = baseline_end - self._baseline_frames

        if baseline_start < 0:
            return None

        values = np.asarray(
            brightness[baseline_start:baseline_end],
            dtype=np.float64,
        )
        values = values[np.isfinite(values)]

        if values.size < self._baseline_frames:
            return None

        baseline_level = float(np.median(values))
        mad = float(
            np.median(
                np.abs(values - baseline_level)
            )
        )

        baseline_tolerance = max(
            self._baseline_minimum_tolerance,
            mad * self._baseline_mad_multiplier,
        )

        return baseline_level, baseline_tolerance

    def _find_return_to_baseline(
        self,
        brightness: np.ndarray,
        search_start: int,
        search_end: int,
        baseline_level: float,
        baseline_tolerance: float,
    ) -> int | None:
        required = self._return_to_baseline_frames

        if required <= 0:
            return search_start

        run_start: int | None = None
        run_length = 0

        for index in range(search_start, search_end):
            value = float(brightness[index])

            in_baseline = (
                np.isfinite(value)
                and abs(value - baseline_level) <= baseline_tolerance
            )

            if in_baseline:
                if run_start is None:
                    run_start = index
                run_length += 1

                if run_length >= required:
                    return run_start
            else:
                run_start = None
                run_length = 0

        return None

    def _search_region(
        self,
        brightness_delta: np.ndarray,
        region_start: int,
        region_end: int,
        effective_threshold: float,
    ) -> tuple[int, int, int, int] | None:
        region_length = region_end - region_start

        if region_length < self._window_frames:
            return None

        last_start = region_end - self._window_frames

        for start_index in range(region_start, last_start + 1):
            end_index = start_index + self._window_frames
            window = brightness_delta[start_index:end_index]

            meaningful_samples, sign_changes = self._measure_window(
                window,
                effective_threshold,
            )

            if (
                meaningful_samples >= self._minimum_meaningful_samples
                and sign_changes >= self._minimum_sign_changes
            ):
                return (
                    start_index,
                    end_index,
                    meaningful_samples,
                    sign_changes,
                )

        return None

    def _measure_window(
        self,
        window: np.ndarray,
        effective_threshold: float,
    ) -> tuple[int, int]:
        meaningful_samples = 0
        sign_changes = 0
        previous_sign = 0

        for delta in window:
            value = float(delta)

            if not np.isfinite(value):
                continue

            if abs(value) < effective_threshold:
                continue

            meaningful_samples += 1
            current_sign = 1 if value > 0.0 else -1

            if previous_sign != 0 and current_sign != previous_sign:
                sign_changes += 1

            previous_sign = current_sign

        return meaningful_samples, sign_changes
