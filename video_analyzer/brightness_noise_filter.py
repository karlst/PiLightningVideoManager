"""Reject candidates containing sustained brightness-delta oscillation."""

from __future__ import annotations

import numpy as np

from video_analyzer.solution_types import SolutionResult


class BrightnessNoiseFilter:
    """Reject candidates with strongly oscillating brightness delta."""

    _WINDOW_FRAMES = 100
    _MIN_SIGN_CHANGES = 80

    def evaluate(
        self,
        brightness: np.ndarray,
        brightness_delta: np.ndarray,
        trigger_frame_index: int | None,
    ) -> SolutionResult:
        _ = brightness
        _ = trigger_frame_index

        max_sign_changes = self._find_max_sign_changes(
            brightness_delta
        )

        if max_sign_changes >= self._MIN_SIGN_CHANGES:
            return SolutionResult(
                is_solution=False,
                reason=(
                    "Brightness delta oscillation detected: "
                    f"{max_sign_changes} sign changes in "
                    f"{self._WINDOW_FRAMES} frames"
                ),
            )

        return SolutionResult(
            is_solution=True,
            reason="Brightness noise filter passed",
        )

    def _find_max_sign_changes(
        self,
        brightness_delta: np.ndarray,
    ) -> int:
        """Return the largest sign-change count in any 100-frame window."""

        frame_count = len(brightness_delta)

        if frame_count < self._WINDOW_FRAMES:
            return 0

        max_sign_changes = 0

        for start_index in range(
            0,
            frame_count - self._WINDOW_FRAMES + 1,
        ):
            end_index = (
                start_index +
                self._WINDOW_FRAMES
            )

            window = brightness_delta[
                start_index:end_index
            ]

            sign_changes = 0

            previous_sign = self._get_sign(
                float(window[0])
            )

            for delta in window[1:]:
                current_sign = self._get_sign(
                    float(delta)
                )

                if (
                    previous_sign != 0 and
                    current_sign != 0 and
                    current_sign != previous_sign
                ):
                    sign_changes += 1

                if current_sign != 0:
                    previous_sign = current_sign

            max_sign_changes = max(
                max_sign_changes,
                sign_changes,
            )

            if max_sign_changes >= self._MIN_SIGN_CHANGES:
                break

        return max_sign_changes

    def _get_sign(
        self,
        value: float,
    ) -> int:
        if value > 0.0:
            return 1

        if value < 0.0:
            return -1

        return 0
