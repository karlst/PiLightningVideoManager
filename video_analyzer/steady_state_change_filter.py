"""Reject candidates containing a persistent brightness level change."""

from __future__ import annotations

import numpy as np

from video_analyzer.solution_types import SolutionResult


class SteadyStateChangeFilter:
    """Reject a brightness jump followed by a sustained new steady state."""

    _JUMP_THRESHOLD = 4.0
    _NEIGHBORHOOD = 2.0
    _MIN_STEADY_FRAMES = 100

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
                original_brightness,
                new_brightness,
            ) = result

            return SolutionResult(
                is_solution=False,
                category="STEADY_STATE_CHANGE",
                reason=(
                    "Steady-state brightness change detected: "
                    f"frame {jump_frame + 1}, "
                    f"{original_brightness:.3f} -> "
                    f"{new_brightness:.3f}"
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

        if frame_count < self._MIN_STEADY_FRAMES + 1:
            return None

        for index in range(1, frame_count):
            original_brightness = float(
                brightness[index - 1]
            )

            new_brightness = float(
                brightness[index]
            )

            jump = abs(
                new_brightness -
                original_brightness
            )

            if jump < self._JUMP_THRESHOLD:
                continue

            end_index = (
                index +
                self._MIN_STEADY_FRAMES
            )

            if end_index > frame_count:
                continue

            steady_frames = brightness[
                index:end_index
            ]

            if np.all(
                np.abs(
                    steady_frames -
                    new_brightness
                ) <= self._NEIGHBORHOOD
            ):
                return (
                    index,
                    original_brightness,
                    new_brightness,
                )

        return None