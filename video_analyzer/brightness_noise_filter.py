"""
Detect sustained brightness-delta oscillation away from the trigger event.

Brightness noise is defined here as repeated positive/negative changes
of meaningful magnitude over a substantial number of frames.

The actual Candidate event is deliberately excluded from this test.
Lightning itself can produce several large positive and negative deltas
near the trigger, and those should not be mistaken for background noise.

The filter therefore:

1. Excludes a configurable number of frames on both sides of the trigger.

2. Searches the remaining pre-trigger and post-trigger regions using
   sliding windows.

3. Ignores brightness deltas whose absolute magnitude is smaller than
   the configured minimum meaningful delta.

4. Counts how many meaningful samples occur in each window.

5. Counts how many times the sign changes among those meaningful samples.

6. Rejects the Candidate as brightness noise only when BOTH:
       - enough meaningful samples exist, and
       - enough sign changes occur.

This distinguishes sustained oscillation:

    +4, -5, +3.5, -4, +6, -3, ...

from ordinary sensor jitter:

    +0.1, -0.2, +0.1, -0.1, ...

and from a short lightning transient near the trigger.
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
        trigger_exclusion_frames: int = 10,
        minimum_delta_magnitude: float = 3.0,
        minimum_meaningful_samples: int = 50,
        minimum_sign_changes: int = 40,
    ) -> None:

        # Width of each sliding region examined for sustained noise.
        self._window_frames = int(
            window_frames
        )

        # Frames this close to the trigger are ignored.
        #
        # Example with trigger T and exclusion 10:
        #
        #     ... inspect ... | T-10 ... T ... T+10 | ... inspect ...
        #
        # The center region contains the actual Candidate event and
        # must not contribute to the brightness-noise decision.
        self._trigger_exclusion_frames = int(
            trigger_exclusion_frames
        )

        # A brightness delta participates in the noise test only when
        # its magnitude is at least this large.
        #
        # Starting value: 3.0 brightness units.
        self._minimum_delta_magnitude = float(
            minimum_delta_magnitude
        )

        # A window must contain this many meaningful delta samples
        # before it can be considered sustained noise.
        self._minimum_meaningful_samples = int(
            minimum_meaningful_samples
        )

        # Among the meaningful samples, require at least this many
        # positive-to-negative or negative-to-positive transitions.
        self._minimum_sign_changes = int(
            minimum_sign_changes
        )

    def evaluate(
        self,
        brightness: np.ndarray,
        brightness_delta: np.ndarray,
        trigger_frame_index: int | None,
    ) -> SolutionResult:
        # This filter works entirely from brightness delta.
        _ = brightness

        result = self._find_noise_window(
            brightness_delta,
            trigger_frame_index,
        )

        if result is not None:
            (
                start_index,
                end_index,
                meaningful_samples,
                sign_changes,
            ) = result

            return SolutionResult(
                is_solution=False,
                category=CATEGORY_BRIGHT_NOISE,
                reason=(
                    "Brightness noise detected: "
                    f"frames {start_index + 1}-{end_index}, "
                    f"{meaningful_samples} deltas with "
                    f"|delta| >= "
                    f"{self._minimum_delta_magnitude:.3f}, "
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
        brightness_delta: np.ndarray,
        trigger_frame_index: int | None,
    ) -> tuple[int, int, int, int] | None:
        """
        Search pre-trigger and post-trigger regions for sustained noise.

        Return:
            start frame index,
            end frame index,
            meaningful sample count,
            sign-change count

        Return None when no qualifying noise region is found.
        """

        frame_count = len(
            brightness_delta
        )

        if frame_count == 0:
            return None

        # Without a valid trigger we cannot safely identify the event
        # neighborhood that must be excluded.
        if trigger_frame_index is None:
            return None

        if not (
            0 <= trigger_frame_index < frame_count
        ):
            return None

        # ----------------------------------------------------------
        # Build the two regions where noise is allowed to count.
        #
        # Everything around the trigger is deliberately omitted.
        # ----------------------------------------------------------

        exclusion_start = max(
            0,
            trigger_frame_index -
            self._trigger_exclusion_frames,
        )

        exclusion_end = min(
            frame_count,
            trigger_frame_index +
            self._trigger_exclusion_frames +
            1,
        )

        regions = [
            (
                0,
                exclusion_start,
            ),
            (
                exclusion_end,
                frame_count,
            ),
        ]

        # Search each side independently. A sliding window is never
        # allowed to cross through the excluded Candidate event.
        for (
            region_start,
            region_end,
        ) in regions:

            result = self._search_region(
                brightness_delta,
                region_start,
                region_end,
            )

            if result is not None:
                return result

        return None

    def _search_region(
        self,
        brightness_delta: np.ndarray,
        region_start: int,
        region_end: int,
    ) -> tuple[int, int, int, int] | None:
        """Search one contiguous region using sliding windows."""

        region_length = (
            region_end -
            region_start
        )

        if region_length < self._window_frames:
            return None

        last_start = (
            region_end -
            self._window_frames
        )

        for start_index in range(
            region_start,
            last_start + 1,
        ):
            end_index = (
                start_index +
                self._window_frames
            )

            window = brightness_delta[
                start_index:end_index
            ]

            (
                meaningful_samples,
                sign_changes,
            ) = self._measure_window(
                window
            )

            # Both persistence and oscillation are required.
            #
            # A few huge lightning deltas do not satisfy the sample
            # count requirement, while tiny sensor jitter does not
            # satisfy the minimum magnitude requirement.
            if (
                meaningful_samples >=
                self._minimum_meaningful_samples
                and
                sign_changes >=
                self._minimum_sign_changes
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
    ) -> tuple[int, int]:
        """
        Count meaningful samples and sign changes in one window.

        Samples with |delta| below the configured threshold are ignored.
        Sign changes are counted only between successive meaningful samples.
        """

        meaningful_samples = 0
        sign_changes = 0
        previous_sign = 0

        for delta in window:
            value = float(
                delta
            )

            # Ignore ordinary small brightness fluctuations.
            if (
                abs(value) <
                self._minimum_delta_magnitude
            ):
                continue

            meaningful_samples += 1

            current_sign = (
                1
                if value > 0.0
                else -1
            )

            # Compare only meaningful samples. Small ignored samples
            # between them do not reset the sign history.
            if (
                previous_sign != 0
                and
                current_sign != previous_sign
            ):
                sign_changes += 1

            previous_sign = (
                current_sign
            )

        return (
            meaningful_samples,
            sign_changes,
        )