"""
Detect steady-state brightness changes after a Candidate trigger.

A steady-state anomaly (SSA) is an event where the scene changes
from its pre-trigger brightness level to a new, persistently elevated
brightness level. An artificial light being switched on is the
canonical example.

This filter is intentionally anchored to the Candidate trigger.
It does NOT scan the entire clip looking for arbitrary brightness
changes.

Algorithm:

1. Calculate the pre-trigger baseline from N frames immediately
   before the trigger.

2. Starting at the trigger, examine only a limited number of
   post-trigger frames.

3. If brightness returns to within +/- R of the original baseline,
   the event is a transient and CANNOT be an SSA. Stop immediately.
   Anything occurring later in the clip is irrelevant to this test.

4. Otherwise, look for brightness that has risen by at least the
   configured amount above the original baseline.

5. Once sufficiently elevated, determine whether brightness remains
   within a configured neighborhood for a configured number of frames.

6. If it does, reject the Candidate as a steady-state anomaly.
"""

from __future__ import annotations

import numpy as np

from video_analyzer.solution_types import SolutionResult


class SteadyStateChangeFilter:
    """Reject Candidates that transition to a persistent elevated level."""

    def __init__(
        self,
        baseline_frames: int,
        baseline_tolerance: float,
        rise_threshold: float,
        steady_neighborhood: float,
        min_steady_frames: int,
        search_frames: int,
    ) -> None:
        # Number of frames immediately BEFORE the Candidate trigger
        # used to calculate the original scene brightness.
        self._baseline_frames = int(
            baseline_frames
        )

        # R in the algorithm above.
        #
        # If post-trigger brightness ever gets this close to the
        # original baseline, the event is considered a transient,
        # not a steady-state change.
        self._baseline_tolerance = float(
            baseline_tolerance
        )

        # Minimum amount that brightness must be ABOVE the original
        # baseline before it can represent a new elevated state.
        #
        # This is NOT an adjacent-frame brightness delta. A gradual
        # rise can therefore still qualify.
        self._rise_threshold = float(
            rise_threshold
        )

        # Maximum allowed variation around the proposed new steady
        # brightness level.
        self._steady_neighborhood = float(
            steady_neighborhood
        )

        # Number of consecutive frames that must remain near the
        # proposed new brightness level before we call it steady.
        self._min_steady_frames = int(
            min_steady_frames
        )

        # Maximum number of frames after the trigger that this filter
        # will examine. Events later than this are ignored.
        self._search_frames = int(
            search_frames
        )

    def evaluate(
        self,
        brightness: np.ndarray,
        brightness_delta: np.ndarray,
        trigger_frame_index: int | None,
    ) -> SolutionResult:
        # This filter operates on absolute brightness relative to the
        # pre-trigger baseline. It deliberately does not use the
        # adjacent-frame brightness-delta array.
        _ = brightness_delta

        result = self._find_steady_state_change(
            brightness,
            trigger_frame_index,
        )

        # A returned result means we found a persistent elevated
        # brightness level that satisfies the SSA definition.
        if result is not None:
            (
                transition_frame,
                baseline_brightness,
                steady_brightness,
            ) = result

            return SolutionResult(
                is_solution=False,
                category="STEADY_STATE_CHANGE",
                reason=(
                    "Steady-state brightness change detected: "
                    f"frame {transition_frame + 1}, "
                    f"baseline {baseline_brightness:.3f} -> "
                    f"steady {steady_brightness:.3f}; "
                    f"increase "
                    f"{steady_brightness - baseline_brightness:.3f}"
                ),
            )

        # Nothing satisfying the SSA definition was found.
        return SolutionResult(
            is_solution=True,
            category="TRUE_FLASH",
            reason="Steady-state change filter passed",
        )

    def _find_steady_state_change(
        self,
        brightness: np.ndarray,
        trigger_frame_index: int | None,
    ) -> tuple[int, float, float] | None:

        # Without a Candidate trigger we don't know where to anchor
        # the pre-trigger baseline or begin the post-trigger search.
        if trigger_frame_index is None:
            return None

        frame_count = len(
            brightness
        )

        # We need enough frames before the trigger to calculate the
        # requested baseline. Also reject an invalid trigger index.
        if (
            trigger_frame_index < self._baseline_frames
            or trigger_frame_index >= frame_count
        ):
            return None

        # ----------------------------------------------------------
        # STEP 1: Establish the original pre-trigger baseline.
        #
        # Example with baseline_frames == 10 and trigger == 260:
        #
        #     frames 250 ... 259 -> mean -> baseline
        #     frame  260         -> trigger/start of search
        # ----------------------------------------------------------

        baseline_start = (
            trigger_frame_index -
            self._baseline_frames
        )

        baseline_samples = brightness[
            baseline_start:
            trigger_frame_index
        ]

        baseline_brightness = float(
            np.mean(
                baseline_samples
            )
        )

        # ----------------------------------------------------------
        # STEP 2: Define the post-trigger region we are willing
        # to examine.
        #
        # We intentionally do NOT scan the rest of the entire clip.
        # ----------------------------------------------------------

        search_end = min(
            frame_count,
            trigger_frame_index +
            self._search_frames,
        )

        # Brightness must reach at least this level before it can
        # represent the proposed new elevated steady state.
        elevated_threshold = (
            baseline_brightness +
            self._rise_threshold
        )

        # Define the "returned to baseline" neighborhood.
        #
        # If baseline = 150 and tolerance = 2:
        #
        #     148 <= brightness <= 152
        #
        # means that the scene has returned to baseline.
        return_low = (
            baseline_brightness -
            self._baseline_tolerance
        )

        return_high = (
            baseline_brightness +
            self._baseline_tolerance
        )

        # ----------------------------------------------------------
        # STEP 3: Walk forward beginning AT the Candidate trigger.
        # ----------------------------------------------------------

        for index in range(
            trigger_frame_index,
            search_end,
        ):
            current_brightness = float(
                brightness[index]
            )

            # ------------------------------------------------------
            # MOST IMPORTANT TRANSIENT RULE:
            #
            # If brightness returns to the original baseline
            # neighborhood, this event cannot be an SSA.
            #
            # Example:
            #
            #     baseline -> flash spike -> baseline
            #
            # That is transient behavior. Stop immediately.
            #
            # We intentionally don't care what happens later.
            # ------------------------------------------------------

            if (
                return_low <=
                current_brightness <=
                return_high
            ):
                return None

            # ------------------------------------------------------
            # The scene has not returned to baseline, but it also
            # hasn't become sufficiently brighter than baseline yet.
            #
            # Keep looking.
            # ------------------------------------------------------

            if (
                current_brightness <
                elevated_threshold
            ):
                continue

            # ------------------------------------------------------
            # We have found a frame sufficiently above baseline.
            #
            # Treat this as a possible beginning of the new steady
            # state and examine the following min_steady_frames.
            # ------------------------------------------------------

            steady_end = (
                index +
                self._min_steady_frames
            )

            # There aren't enough frames left inside our configured
            # search region to prove that this level persists.
            if steady_end > search_end:
                continue

            steady_samples = brightness[
                index:steady_end
            ]

            # Use the mean of the proposed steady region as its
            # representative brightness level.
            steady_brightness = float(
                np.mean(
                    steady_samples
                )
            )

            # The mean of the proposed steady region must itself
            # remain sufficiently elevated above the ORIGINAL
            # pre-trigger baseline.
            if (
                steady_brightness <
                elevated_threshold
            ):
                continue

            # ------------------------------------------------------
            # STEP 4: Decide whether this is actually steady.
            #
            # Every frame in the proposed steady region must remain
            # within +/- steady_neighborhood of that region's mean.
            #
            # Example:
            #
            #     steady mean = 117
            #     neighborhood = 2
            #
            # Every frame must be between 115 and 119.
            # ------------------------------------------------------

            is_steady = bool(
                np.all(
                    np.abs(
                        steady_samples -
                        steady_brightness
                    )
                    <=
                    self._steady_neighborhood
                )
            )

            # ------------------------------------------------------
            # We have now found:
            #
            #   * no return to baseline,
            #   * an increase sufficiently above baseline, and
            #   * a persistent stable elevated level.
            #
            # That satisfies our current definition of an SSA.
            # ------------------------------------------------------

            if is_steady:
                return (
                    index,
                    baseline_brightness,
                    steady_brightness,
                )

        # We exhausted the post-trigger search region without
        # satisfying the SSA definition.
        return None