"""
Detect strong positive transient evidence near the Candidate trigger.

This filter is intended primarily for strong night lightning flashes.

Current definition of a strong transient:

1. Near the Candidate trigger, find a large POSITIVE brightness delta.

2. Within the following N frames, find a large NEGATIVE brightness delta.

3. The positive and negative magnitudes do not need to be symmetrical.

Example:

    +80
      ...
      ...
    -55

within 10 frames qualifies.

The idea is that a strong flash produces a rapid increase in scene
brightness followed shortly by a rapid decrease.

This is POSITIVE evidence for a real flash. If this pattern is found,
SolutionFilter should accept the Candidate immediately and NOT allow
later brightness-noise or steady-state filters to reject it.

Frame-dropout filtering must run BEFORE this test because a dropout
recovery can also create a very large positive brightness delta.
"""

from __future__ import annotations

import numpy as np

from video_analyzer.solution_types import CATEGORY_TRUE_FLASH
from video_analyzer.solution_types import SolutionResult


class StrongTransientFilter:
    """Identify a large positive/negative transient near the trigger."""

    # Large positive brightness change required to start the transient.
    _POSITIVE_DELTA_THRESHOLD = 50.0

    # Large negative brightness change required shortly afterward.
    _NEGATIVE_DELTA_THRESHOLD = -50.0

    # Once the large positive delta is found, the large negative delta
    # must occur within this many following frames.
    _MAX_RETURN_FRAMES = 10

    # Search a few frames before the Candidate trigger because the Pi
    # trigger may occur slightly after the true beginning of the flash.
    _TRIGGER_SEARCH_BEFORE = 3

    # Also search a short distance after the trigger for the initial
    # large positive delta.
    _TRIGGER_SEARCH_AFTER = 10

    def evaluate(
        self,
        brightness: np.ndarray,
        brightness_delta: np.ndarray,
        trigger_frame_index: int | None,
    ) -> SolutionResult:
        # This detector works entirely from adjacent-frame brightness
        # delta. Absolute brightness is not needed.
        _ = brightness

        result = self._find_strong_transient(
            brightness_delta,
            trigger_frame_index,
        )

        if result is not None:
            (
                positive_frame,
                positive_delta,
                negative_frame,
                negative_delta,
            ) = result

            return SolutionResult(
                is_solution=True,
                category=CATEGORY_TRUE_FLASH,
                reason=(
                    "Strong transient detected: "
                    f"frame {positive_frame + 1} "
                    f"delta {positive_delta:+.3f}, "
                    f"frame {negative_frame + 1} "
                    f"delta {negative_delta:+.3f}"
                ),
            )

        # This result does NOT mean the Candidate is false.
        #
        # It only means this particular strong-transient signature
        # was not found. SolutionFilter may continue with its normal
        # rejection filters.
        return SolutionResult(
            is_solution=False,
            category="NO_STRONG_TRANSIENT",
            reason="Strong transient not detected",
        )

    def _find_strong_transient(
        self,
        brightness_delta: np.ndarray,
        trigger_frame_index: int | None,
    ) -> tuple[int, float, int, float] | None:
        """
        Look for:

            large positive delta
                    followed within N frames by
            large negative delta

        near the Candidate trigger.
        """

        if trigger_frame_index is None:
            return None

        frame_count = len(
            brightness_delta
        )

        if not (
            0 <= trigger_frame_index < frame_count
        ):
            return None

        # ----------------------------------------------------------
        # Define the small neighborhood in which the initial strong
        # positive delta is allowed to occur.
        #
        # With trigger T:
        #
        #     T-3 ... T ... T+10
        #
        # We deliberately do NOT search the whole clip.
        # ----------------------------------------------------------

        positive_search_start = max(
            0,
            trigger_frame_index -
            self._TRIGGER_SEARCH_BEFORE,
        )

        positive_search_end = min(
            frame_count,
            trigger_frame_index +
            self._TRIGGER_SEARCH_AFTER +
            1,
        )

        for positive_frame in range(
            positive_search_start,
            positive_search_end,
        ):
            positive_delta = float(
                brightness_delta[
                    positive_frame
                ]
            )

            # This frame must contain a sufficiently large positive
            # brightness change.
            if (
                positive_delta <=
                self._POSITIVE_DELTA_THRESHOLD
            ):
                continue

            # ------------------------------------------------------
            # We found the strong upward transition.
            #
            # Now look only a short distance forward for the strong
            # downward transition that completes the transient.
            # ------------------------------------------------------

            negative_search_start = (
                positive_frame + 1
            )

            negative_search_end = min(
                frame_count,
                positive_frame +
                self._MAX_RETURN_FRAMES +
                1,
            )

            for negative_frame in range(
                negative_search_start,
                negative_search_end,
            ):
                negative_delta = float(
                    brightness_delta[
                        negative_frame
                    ]
                )

                if (
                    negative_delta <
                    self._NEGATIVE_DELTA_THRESHOLD
                ):
                    return (
                        positive_frame,
                        positive_delta,
                        negative_frame,
                        negative_delta,
                    )

        return None