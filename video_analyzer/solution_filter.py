"""
Run the desktop-only Solution filters.

Filter order is intentional.

1. FrameDropoutFilter runs first because a frame dropout can produce
   an enormous positive recovery delta. We must eliminate that known
   camera anomaly before treating a large positive/negative pair as
   strong lightning evidence.

2. StairStepDecayFilter rejects the camera artifact where a large positive
   jump falls back through several negative steps and returns near baseline.

   It must run before StrongTransientFilter because the same large positive
   and negative deltas can otherwise resemble strong lightning evidence.

3. StrongTransientFilter then looks for strong positive evidence of a
   real flash near the Candidate trigger.

   If found, the Candidate is immediately accepted as a Solution.
   Later rejection filters are NOT allowed to override it.

4. If the Candidate was selected by the bright-pixel trigger and no strong
   transient was proven, BrightPixelNoReturnFilter rejects a persistent step
   away from the pre-trigger brightness trend.

5. Continue with the ordinary false-positive rejection filters:
       - brightness noise
       - steady-state change
"""

from __future__ import annotations

import numpy as np

from video_analyzer.bright_pixel_no_return_filter import BrightPixelNoReturnFilter
from video_analyzer.brightness_noise_filter import BrightnessNoiseFilter
from video_analyzer.frame_dropout_filter import FrameDropoutFilter
from video_analyzer.solution_config import SOLUTION_CONFIG
from video_analyzer.solution_config import SolutionConfig
from video_analyzer.stair_step_decay_filter import StairStepDecayFilter
from video_analyzer.steady_state_change_filter import SteadyStateChangeFilter
from video_analyzer.strong_transient_filter import StrongTransientFilter
from video_analyzer.solution_types import CATEGORY_FAILED_CANDIDATE
from video_analyzer.solution_types import CATEGORY_TRUE_FLASH
from video_analyzer.solution_types import SolutionResult
from video_analyzer.solution_types import SolutionRule


def failed_candidate_result() -> SolutionResult:
    """Return the pipeline result used when Stage 1 selects no Candidate."""

    return SolutionResult(
        is_solution=False,
        category=CATEGORY_FAILED_CANDIDATE,
        reason="Failed candidate selection",
    )


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
        # Stair-step decay is a known camera false-positive family.
        #
        # It must run before StrongTransient because the stair-step
        # artifact starts with a large positive jump and then produces
        # several substantial negative deltas.
        # ----------------------------------------------------------

        self._stair_step_decay_filter = (
            StairStepDecayFilter()
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
        # Bright-pixel no-return is specific to Candidates selected
        # by CandidateFinder's bright-pixel trigger.
        # ----------------------------------------------------------

        self._bright_pixel_no_return_filter = (
            BrightPixelNoReturnFilter()
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
        trigger_reason: str = "",
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
        # STEP 2: Eliminate stair-step decay anomalies.
        #
        # This must happen before strong-transient detection.
        # ----------------------------------------------------------

        stair_step_result = (
            self._stair_step_decay_filter.evaluate(
                brightness,
                brightness_delta,
                trigger_frame_index,
            )
        )

        if not stair_step_result.is_solution:
            return stair_step_result

        # ----------------------------------------------------------
        # STEP 3: Look for strong positive lightning evidence.
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
        # STEP 4: Bright-pixel-specific no-return test.
        #
        # CandidateFinder's reason is passed in by the caller. Only
        # bright-pixel Candidates are subject to this filter.
        # ----------------------------------------------------------

        if "bright pixel trigger" in trigger_reason.lower():
            no_return_result = (
                self._bright_pixel_no_return_filter.evaluate(
                    brightness,
                    brightness_delta,
                    trigger_frame_index,
                )
            )

            if not no_return_result.is_solution:
                return no_return_result

        # ----------------------------------------------------------
        # STEP 5: No strong transient or bright-pixel no-return
        # rejection was proven.
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