"""
Run the desktop-only Solution filters.

Filter order is intentional.

1. FrameDropoutFilter runs first because a frame dropout can produce
   an enormous positive recovery delta. We must eliminate that known
   camera anomaly before treating a large positive/negative pair as
   strong lightning evidence.

2. StrongTransientFilter then looks for strong positive evidence of a
   real flash near the Candidate trigger.

   If found, the Candidate is immediately accepted as a Solution.
   Later rejection filters are NOT allowed to override it.

3. If no strong transient is found, continue with the ordinary
   false-positive rejection filters:
       - brightness noise
       - steady-state change
"""

from __future__ import annotations

import numpy as np

from video_analyzer.brightness_noise_filter import BrightnessNoiseFilter
from video_analyzer.frame_dropout_filter import FrameDropoutFilter
from video_analyzer.solution_config import SOLUTION_CONFIG
from video_analyzer.solution_config import SolutionConfig
from video_analyzer.steady_state_change_filter import SteadyStateChangeFilter
from video_analyzer.strong_transient_filter import StrongTransientFilter
from video_analyzer.solution_types import CATEGORY_TRUE_FLASH
from video_analyzer.solution_types import SolutionResult
from video_analyzer.solution_types import SolutionRule


class SolutionFilter:
    """Classify a Candidate using positive evidence and rejection filters."""

    def __init__(
        self,
        config: SolutionConfig = SOLUTION_CONFIG,
    ) -> None:

        # ----------------------------------------------------------
        # FDA is handled separately and FIRST.
        #
        # A dropout/recovery can produce very large brightness deltas
        # that might otherwise look like a strong transient.
        # ----------------------------------------------------------

        self._frame_dropout_filter = (
            FrameDropoutFilter()
        )

        # ----------------------------------------------------------
        # Strong transient is POSITIVE evidence.
        #
        # If this succeeds, SolutionFilter immediately accepts the
        # Candidate and never runs the remaining rejection filters.
        # ----------------------------------------------------------

        self._strong_transient_filter = (
            StrongTransientFilter()
        )

        # ----------------------------------------------------------
        # Remaining filters are ordinary FALSE-POSITIVE detectors.
        #
        # They run only when no strong transient has already proven
        # the Candidate sufficiently interesting.
        # ----------------------------------------------------------

        self._rejection_filters: list[
            SolutionRule
        ] = [

            BrightnessNoiseFilter(
                window_frames=(
                    config.
                    brightness_noise_window_frames
                ),
                trigger_exclusion_frames=(
                    config.
                    brightness_noise_trigger_exclusion_frames
                ),
                minimum_delta_magnitude=(
                    config.
                    brightness_noise_min_delta_magnitude
                ),
                minimum_meaningful_samples=(
                    config.
                    brightness_noise_min_meaningful_samples
                ),
                minimum_sign_changes=(
                    config.
                    brightness_noise_min_sign_changes
                ),
            ),

            SteadyStateChangeFilter(
                baseline_frames=(
                    config.
                    steady_state_baseline_frames
                ),
                baseline_tolerance=(
                    config.
                    steady_state_baseline_tolerance
                ),
                rise_threshold=(
                    config.
                    steady_state_rise_threshold
                ),
                steady_neighborhood=(
                    config.
                    steady_state_neighborhood
                ),
                min_steady_frames=(
                    config.
                    steady_state_min_frames
                ),
                search_frames=(
                    config.
                    steady_state_search_frames
                ),
            ),
        ]

    def evaluate(
        self,
        brightness: np.ndarray,
        brightness_delta: np.ndarray,
        trigger_frame_index: int | None,
    ) -> SolutionResult:

        # ----------------------------------------------------------
        # STEP 1: Eliminate frame-dropout anomalies.
        #
        # This must happen before strong-transient detection.
        # ----------------------------------------------------------

        dropout_result = (
            self._frame_dropout_filter.evaluate(
                brightness,
                brightness_delta,
                trigger_frame_index,
            )
        )

        if not dropout_result.is_solution:
            return dropout_result

        # ----------------------------------------------------------
        # STEP 2: Look for strong positive lightning evidence.
        #
        # A large positive delta followed within 10 frames by a large
        # negative delta is currently considered sufficiently strong
        # evidence to accept the Candidate immediately.
        # ----------------------------------------------------------

        transient_result = (
            self._strong_transient_filter.evaluate(
                brightness,
                brightness_delta,
                trigger_frame_index,
            )
        )

        if transient_result.is_solution:
            return transient_result

        # ----------------------------------------------------------
        # STEP 3: No strong transient was proven.
        #
        # Allow the normal false-positive filters to examine the
        # Candidate.
        # ----------------------------------------------------------

        for solution_filter in (
            self._rejection_filters
        ):
            result = solution_filter.evaluate(
                brightness,
                brightness_delta,
                trigger_frame_index,
            )

            if not result.is_solution:
                return result

        # ----------------------------------------------------------
        # Nothing identified this Candidate as a known false-positive
        # family, so it remains a Solution.
        # ----------------------------------------------------------

        return SolutionResult(
            is_solution=True,
            category=CATEGORY_TRUE_FLASH,
            reason="All solution filters passed",
        )