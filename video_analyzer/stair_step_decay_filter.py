"""
Reject Candidates with a stair-step brightness decay after the trigger.

This false-positive family has a distinctive shape:

1. A large positive brightness jump occurs at or very near the Candidate trigger.
2. Brightness then falls through several distinct downward events rather
   than returning in one transient drop.
3. Consecutive qualifying negative frames belong to the same downward event.
   Separate events together must recover a substantial fraction of the
   initial positive jump.
4. A substantial positive re-brightening during the decay window disqualifies
   the pattern because a true staircase should remain predominantly one-way.
5. By the end of the short search window, brightness has returned close to the
   pre-trigger baseline.

A real lightning flash may recover over a few frames rather than one frame.
When cumulative negative recovery within the configured short transient window
reaches the configured fraction of the rise, the filter stops and accepts the
event as a transient rather than continuing to accumulate later negative steps.

The filter uses only the brightness arrays already stored in the sidecar; it
does not inspect video frames.
"""

from __future__ import annotations

import numpy as np

from video_analyzer.solution_types import CATEGORY_TRUE_FLASH
from video_analyzer.solution_types import SolutionResult


CATEGORY_STAIR_STEP_DECAY = "STAIR_STEP_DECAY"


class StairStepDecayFilter:
    """Reject a large rise followed by several discrete downward steps."""

    def __init__(
        self,
        baseline_frames: int = 10,
        trigger_search_frames: int = 3,
        minimum_initial_rise: float = 5.0,
        decay_search_frames: int = 35,
        negative_step_threshold: float = 0.40,
        minimum_negative_steps: int = 3,
        minimum_recovery_fraction: float = 0.70,
        baseline_return_tolerance: float = 2.0,
        transient_recovery_frames: int = 4,
        transient_recovery_fraction: float = 0.70,
        step_separation_frames: int = 1,
        rebrightening_fraction: float = 0.30,
    ) -> None:
        self._baseline_frames = int(
            baseline_frames
        )
        self._trigger_search_frames = int(
            trigger_search_frames
        )
        self._minimum_initial_rise = float(
            minimum_initial_rise
        )
        self._decay_search_frames = int(
            decay_search_frames
        )
        self._negative_step_threshold = float(
            negative_step_threshold
        )
        self._minimum_negative_steps = int(
            minimum_negative_steps
        )
        self._minimum_recovery_fraction = float(
            minimum_recovery_fraction
        )
        self._baseline_return_tolerance = float(
            baseline_return_tolerance
        )
        self._transient_recovery_frames = int(
            transient_recovery_frames
        )
        self._transient_recovery_fraction = float(
            transient_recovery_fraction
        )
        self._step_separation_frames = max(
            1,
            int(step_separation_frames),
        )
        self._rebrightening_fraction = float(
            rebrightening_fraction
        )

    # ## Reject the Candidate when a qualifying staircase decay is found.
    def evaluate(
        self,
        brightness: np.ndarray,
        brightness_delta: np.ndarray,
        trigger_frame_index: int | None,
    ) -> SolutionResult:
        result = self._find_stair_step_decay(
            brightness,
            brightness_delta,
            trigger_frame_index,
        )

        if result is not None:
            (
                rise_frame,
                baseline_brightness,
                peak_brightness,
                negative_steps,
                total_negative_recovery,
                return_brightness,
            ) = result

            return SolutionResult(
                is_solution=False,
                category=CATEGORY_STAIR_STEP_DECAY,
                reason=(
                    "Stair-step decay detected: "
                    f"rise frame {rise_frame + 1}, "
                    f"baseline {baseline_brightness:.3f} -> "
                    f"peak {peak_brightness:.3f}; "
                    f"{negative_steps} negative steps; "
                    f"cumulative recovery {total_negative_recovery:.3f}; "
                    f"returned to {return_brightness:.3f}"
                ),
            )

        return SolutionResult(
            is_solution=True,
            category=CATEGORY_TRUE_FLASH,
            reason="Stair-step decay filter passed",
        )

    # ## Search near the Candidate trigger for the staircase false-positive pattern.
    def _find_stair_step_decay(
        self,
        brightness: np.ndarray,
        brightness_delta: np.ndarray,
        trigger_frame_index: int | None,
    ) -> tuple[int, float, float, int, float, float] | None:
        if trigger_frame_index is None:
            return None

        frame_count = len(
            brightness
        )

        if (
            frame_count == 0
            or len(brightness_delta) != frame_count
            or trigger_frame_index < self._baseline_frames
            or trigger_frame_index >= frame_count
        ):
            return None

        baseline_start = (
            trigger_frame_index -
            self._baseline_frames
        )

        baseline_brightness = float(
            np.mean(
                brightness[
                    baseline_start:
                    trigger_frame_index
                ]
            )
        )

        # The Candidate trigger and the large rise can differ by a frame or two,
        # so search a very small neighborhood rather than requiring an exact match.
        rise_search_end = min(
            frame_count,
            trigger_frame_index +
            self._trigger_search_frames +
            1,
        )

        rise_frame = None
        rise_delta = float("-inf")

        for frame_index in range(
            trigger_frame_index,
            rise_search_end,
        ):
            delta = float(
                brightness_delta[
                    frame_index
                ]
            )

            if delta > rise_delta:
                rise_delta = delta
                rise_frame = frame_index

        if (
            rise_frame is None
            or rise_delta < self._minimum_initial_rise
        ):
            return None

        peak_brightness = float(
            brightness[
                rise_frame
            ]
        )

        # A real flash can recover over several frames. Measure cumulative
        # negative recovery during a very short transient window immediately
        # after the rise. Small negative deltas count here too; this test asks
        # only whether the signal returned quickly, not whether each change is
        # large enough to qualify as a stair-step.
        transient_end = min(
            frame_count,
            rise_frame +
            self._transient_recovery_frames +
            1,
        )

        transient_recovery = 0.0

        for frame_index in range(
            rise_frame + 1,
            transient_end,
        ):
            delta = float(
                brightness_delta[
                    frame_index
                ]
            )

            if delta < 0.0:
                transient_recovery += -delta

        if (
            transient_recovery >=
            rise_delta *
            self._transient_recovery_fraction
        ):
            return None

        decay_end = min(
            frame_count,
            rise_frame +
            self._decay_search_frames +
            1,
        )

        # Stair-step decay should be predominantly one-way after the initial
        # rise. A substantial later positive pulse is evidence of a multi-pulse
        # transient, so stop stair-step detection immediately.
        rebrightening_threshold = (
            rise_delta *
            self._rebrightening_fraction
        )

        for frame_index in range(
            rise_frame + 1,
            decay_end,
        ):
            delta = float(
                brightness_delta[
                    frame_index
                ]
            )

            if (
                delta >=
                rebrightening_threshold
            ):
                return None

        negative_steps = 0
        total_negative_recovery = 0.0

        # Count distinct downward events, not individual negative frames.
        # Consecutive qualifying negative deltas are one event. A new event
        # begins only after the configured number of intervening non-step
        # frames, which represents the plateau between staircase drops.
        in_negative_event = False
        non_step_frames = 0

        for frame_index in range(
            rise_frame + 1,
            decay_end,
        ):
            delta = float(
                brightness_delta[
                    frame_index
                ]
            )

            if (
                delta <=
                -self._negative_step_threshold
            ):
                total_negative_recovery += -delta

                if not in_negative_event:
                    negative_steps += 1
                    in_negative_event = True

                non_step_frames = 0
                continue

            if in_negative_event:
                non_step_frames += 1

                if (
                    non_step_frames >=
                    self._step_separation_frames
                ):
                    in_negative_event = False
                    non_step_frames = 0

        if (
            negative_steps <
            self._minimum_negative_steps
        ):
            return None

        if (
            total_negative_recovery <
            rise_delta * self._minimum_recovery_fraction
        ):
            return None

        # Require the staircase to settle back near the original baseline.
        # Use the last few available frames in the search window rather than
        # one frame so a tiny amount of noise does not control the decision.
        return_window_start = max(
            rise_frame + 1,
            decay_end - 5,
        )

        return_brightness = float(
            np.mean(
                brightness[
                    return_window_start:
                    decay_end
                ]
            )
        )

        if (
            abs(
                return_brightness -
                baseline_brightness
            ) >
            self._baseline_return_tolerance
        ):
            return None

        return (
            rise_frame,
            baseline_brightness,
            peak_brightness,
            negative_steps,
            total_negative_recovery,
            return_brightness,
        )
