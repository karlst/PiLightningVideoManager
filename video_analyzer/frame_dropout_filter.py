"""
Detect a frame-dropout anomaly immediately before the Candidate trigger.

A frame-dropout anomaly has this characteristic pattern:

    normal image brightness
        ->
    sudden collapse to nearly black
        ->
    Candidate trigger

The Candidate trigger already tells us that a positive event occurred
after the dropout. Therefore this filter does NOT attempt to verify
recovery or examine what happens after the trigger.

The important distinction is between:

    brightness 100 -> 2     possible frame dropout

and:

    brightness   2 -> 2     naturally dark scene, NOT a dropout

Therefore a frame must satisfy BOTH conditions:

1. Its absolute brightness is near zero.
2. Its brightness dropped substantially from the brightness immediately
   preceding it.

Only frames shortly before the Candidate trigger are examined.
"""

from __future__ import annotations

import numpy as np

from video_analyzer.solution_types import SolutionResult


class FrameDropoutFilter:
    """Detect a sudden collapse to nearly black before the trigger."""

    # Examine only this many frames immediately before the Candidate
    # trigger. A dark frame elsewhere in the clip is irrelevant.
    _PRE_TRIGGER_SEARCH_FRAMES = 10

    # A dropout frame must be essentially black.
    _DROPOUT_BRIGHTNESS_THRESHOLD = 5.0

    # A near-black frame is not enough by itself. The image must have
    # actually DROPPED toward black.
    #
    # This prevents a naturally dark scene with brightness around 2
    # from being classified as a dropout.
    _MINIMUM_BRIGHTNESS_DROP = 20.0

    # Use several frames immediately before the possible dropout to
    # establish what the image brightness was before it collapsed.
    #
    # Using three frames instead of one avoids making the decision
    # from a single potentially noisy frame.
    _PRE_DROPOUT_BASELINE_FRAMES = 3

    def evaluate(
        self,
        brightness: np.ndarray,
        brightness_delta: np.ndarray,
        trigger_frame_index: int | None,
    ) -> SolutionResult:
        # FDA detection uses absolute brightness. We do not need the
        # adjacent-frame brightness-delta array.
        _ = brightness_delta

        result = self._find_dropout(
            brightness,
            trigger_frame_index,
        )

        if result is not None:
            (
                dropout_frame,
                pre_dropout_brightness,
                dropout_brightness,
            ) = result

            return SolutionResult(
                is_solution=False,
                category="FRAME_DROPOUT",
                reason=(
                    "Frame dropout detected: "
                    f"frame {dropout_frame + 1}, "
                    f"brightness "
                    f"{pre_dropout_brightness:.3f} -> "
                    f"{dropout_brightness:.3f}"
                ),
            )

        return SolutionResult(
            is_solution=True,
            category="TRUE_FLASH",
            reason="Frame dropout filter passed",
        )

    def _find_dropout(
        self,
        brightness: np.ndarray,
        trigger_frame_index: int | None,
    ) -> tuple[int, float, float] | None:
        # The Candidate trigger anchors the entire FDA search.
        # Without a valid trigger there is nothing useful to examine.
        if trigger_frame_index is None:
            return None

        frame_count = len(
            brightness
        )

        if not (
            0 <= trigger_frame_index < frame_count
        ):
            return None

        # ----------------------------------------------------------
        # Define the small region immediately BEFORE the trigger.
        #
        # For trigger T, examine:
        #
        #     T-10 ... T-1
        #
        # The trigger itself is not part of the dropout search.
        # ----------------------------------------------------------

        search_start = max(
            self._PRE_DROPOUT_BASELINE_FRAMES,
            trigger_frame_index -
            self._PRE_TRIGGER_SEARCH_FRAMES,
        )

        search_end = (
            trigger_frame_index
        )

        for frame_index in range(
            search_start,
            search_end,
        ):
            dropout_brightness = float(
                brightness[frame_index]
            )

            # ------------------------------------------------------
            # First requirement:
            #
            # The possible dropout frame must actually be nearly
            # black. If it isn't, there is no reason to do any
            # further work on this frame.
            # ------------------------------------------------------

            if (
                dropout_brightness >=
                self._DROPOUT_BRIGHTNESS_THRESHOLD
            ):
                continue

            # ------------------------------------------------------
            # Establish the brightness immediately BEFORE the
            # possible dropout.
            #
            # Example:
            #
            #     154  154  153  2
            #     <---------->   ^
            #       baseline     possible dropout
            #
            # The mean of those three preceding frames is our
            # estimate of the brightness before the collapse.
            # ------------------------------------------------------

            baseline_start = (
                frame_index -
                self._PRE_DROPOUT_BASELINE_FRAMES
            )

            pre_dropout_samples = brightness[
                baseline_start:
                frame_index
            ]

            pre_dropout_brightness = float(
                np.mean(
                    pre_dropout_samples
                )
            )

            brightness_drop = (
                pre_dropout_brightness -
                dropout_brightness
            )

            # ------------------------------------------------------
            # Second requirement:
            #
            # The near-black frame must represent a real collapse
            # from a substantially brighter image.
            #
            # Example:
            #
            #     154 -> 2
            #
            # qualifies.
            #
            # But:
            #
            #       2 -> 2
            #
            # does not. That is simply a dark scene.
            # ------------------------------------------------------

            if (
                brightness_drop >=
                self._MINIMUM_BRIGHTNESS_DROP
            ):
                return (
                    frame_index,
                    pre_dropout_brightness,
                    dropout_brightness,
                )

        # No near-black collapse was found in the pre-trigger region.
        return None