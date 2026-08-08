"""Reject candidates containing a persistent brightness level change."""

from __future__ import annotations

import numpy as np

from video_analyzer.solution_types import SolutionResult


class SteadyStateChangeFilter:
    """Reject a brightness jump followed by a sustained new steady state."""

    _JUMP_THRESHOLD = 4.0

    _BASELINE_FRAMES = 10

    _STEADY_NEIGHBORHOOD = 2.0

    _MIN_STEADY_FRAMES = 100

    def __init__(
        self,
        baseline_tolerance: float = 10.0,
    ) -> None:
        self._baseline_tolerance = float(
            baseline_tolerance
        )

    def evaluate(
        self,
        brightness: np.ndarray,
        brightness_delta: np.ndarray,
        trigger_frame_index: int | None,
    ) -> SolutionResult:
        _ = brightness_delta
        _ = trigger_frame_index

        result = self._find_steady_state_change(
            brightness
        )

        if result is not None:
            (
                jump_frame,
                baseline_brightness,
                steady_brightness,
            ) = result

            return SolutionResult(
                is_solution=False,
                category="STEADY_STATE_CHANGE",
                reason=(
                    "Steady-state brightness change detected: "
                    f"frame {jump_frame + 1}, "
                    f"baseline {baseline_brightness:.3f} -> "
                    f"steady {steady_brightness:.3f}; "
                    f"difference "
                    f"{abs(steady_brightness - baseline_brightness):.3f} "
                    f"> tolerance "
                    f"{self._baseline_tolerance:.3f}"
                ),
            )

        return SolutionResult(
            is_solution=True,
            category="TRUE_FLASH",
            reason="Steady-state change filter passed",
        )

    def _find_steady_state_change(
        self,
        brightness: np.ndarray,
    ) -> tuple[int, float, float] | None:

        frame_count = len(brightness)

        minimum_frames = (
            self._BASELINE_FRAMES +
            self._MIN_STEADY_FRAMES
        )

        if frame_count < minimum_frames:
            return None

        for index in range(
            self._BASELINE_FRAMES,
            frame_count,
        ):
            previous_brightness = float(
                brightness[index - 1]
            )

            transition_brightness = float(
                brightness[index]
            )

            jump = abs(
                transition_brightness -
                previous_brightness
            )

            if jump < self._JUMP_THRESHOLD:
                continue

            baseline_start = (
                index -
                self._BASELINE_FRAMES
            )

            baseline_frames = brightness[
                baseline_start:index
            ]

            baseline_brightness = float(
                np.mean(
                    baseline_frames
                )
            )

            steady_end = (
                index +
                self._MIN_STEADY_FRAMES
            )

            if steady_end > frame_count:
                continue

            steady_frames = brightness[
                index:steady_end
            ]

            steady_brightness = float(
                np.mean(
                    steady_frames
                )
            )

            is_steady = np.all(
                np.abs(
                    steady_frames -
                    steady_brightness
                ) <= self._STEADY_NEIGHBORHOOD
            )

            if not is_steady:
                continue

            baseline_difference = abs(
                steady_brightness -
                baseline_brightness
            )

            if (
                baseline_difference <=
                self._baseline_tolerance
            ):
                continue

            return (
                index,
                baseline_brightness,
                steady_brightness,
            )

        return None